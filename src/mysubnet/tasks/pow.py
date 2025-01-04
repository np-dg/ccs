import numpy as np
from numba import cuda, uint64
import time
import random
import string

from .tasks import PowTaskResult


def hash(value: str, nonce: int):
    q = np.uint64(18446744073709551557)
    value = np.uint64(int.from_bytes(value.encode(), "big"))
    k = np.uint64(3472328296227680304)
    c = np.uint64(8241990170776528228)

    nonce = np.uint64(nonce)
    values = [value, nonce]

    def f(x, iv):
        x = x ^ iv
        for _ in range(256):
            x = x ^ k
            x = x ^ c
            x = uint64(x ** 3)
            x = uint64(x % q)

        return x

    iv = 2**64 - 1
    for x in values:
        hash = f(x, iv)
        iv = iv ^ hash

    return hash


@cuda.jit
def pow_kernel(values, nonces, result, target):
    q = uint64(18446744073709551557)
    k = uint64(3472328296227680304)
    c = uint64(8241990170776528228)

    idx = cuda.grid(1)
    if idx < nonces.size:
        nonce = nonces[idx]
        value = cuda.local.array(2, uint64)

        value[0] = uint64(values[0])
        value[1] = uint64(nonce)

        def f(x, iv):
            x = x ^ iv
            for _ in range(256):
                x = x ^ k
                x = x ^ c
                x = uint64(x ** 3)
                x = uint64(x % q)

            return x

        iv = 2**64 - 1
        for x in value:
            hash = f(x, iv)
            iv = iv ^ hash

        if hash < target[0]:
            prev = cuda.atomic.max(result, 1, 1)
            if prev == 0:
                result[0] = nonce


def pow_gpu(data: str, difficulty: int) -> int:
    start_nonce = 0
    batch_size = 10**6

    # Prepare the target
    target_value = 2 ** (64 - difficulty)
    target = np.array([target_value], dtype=np.uint64)
    target_device = cuda.to_device(target)

    # Prepare the result array on the host and device
    result_host = np.zeros(2, dtype=np.uint64)
    result_device = cuda.to_device(result_host)

    while True:
        # Reset the result array to zeros before each kernel launch
        result_host[:] = 0
        result_device.copy_to_device(result_host)

        # Generate a batch of nonces
        nonces = np.arange(start_nonce, start_nonce +
                           batch_size, dtype=np.uint64)
        nonces_device = cuda.to_device(nonces)

        # Prepare value as unsigned 64-bit integer
        value = np.array([
            int.from_bytes(data.encode(), "big")
        ], dtype=np.uint64)
        value_device = cuda.to_device(value)

        # Define CUDA kernel execution configuration
        threads_per_block = 256
        blocks = (nonces.size + threads_per_block - 1) // threads_per_block

        # Launch the CUDA kernel
        pow_kernel[blocks, threads_per_block](
            value_device, nonces_device, result_device, target_device
        )

        # Copy the results back to the host
        result_host = result_device.copy_to_host()

        # Check if a valid nonce was found
        if result_host[1] == 1:
            return result_host[0]

        start_nonce += batch_size


def pow(data, difficulty):
    target = 2 ** (64 - difficulty)
    nonce = 0
    while True:
        candidate = hash(data, nonce)

        if candidate < target:
            return nonce

        nonce += 1


def validate_pow(result: PowTaskResult):
    target_value = 2 ** (64 - result.task.difficulty)
    final_hash = hash(result.task.data + str(result.nonce))
    if final_hash < target_value:
        return True

    return False


if __name__ == "__main__":
    pool = string.ascii_letters + string.digits + string.punctuation
    data = ''.join(random.choice(pool) for _ in range(8))
    difficulty = 3 * 4
    start_time = time.time()
    nonce = pow(data, difficulty)
    end_time = time.time()

    final_hash = hash(data, nonce)

    # Verify that the final hash meets the target condition
    target_value = 2 ** (64 - difficulty)
    assert final_hash < target_value, "Final hash does not meet the target condition."

    print(f"Mining successful for {data} !\nNonce: {nonce}")
    print(f"Initial Hash: {hex(hash(data, 0))[2:].zfill(16)}")
    print(f"Final Hash: {hex(final_hash)[2:].zfill(16)}")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
