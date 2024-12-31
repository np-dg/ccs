from communex.module import Module, endpoint
from communex.key import generate_keypair
from keylimiter import TokenBucketLimiter

from ..tasks.pow import pow_gpu
from ..tasks.tasks import PowTask, PowTaskResult, TaskType


class Miner(Module):
    def __init__(self):
        super().__init__()
        pow_gpu("abcdefgh", 1)

    @endpoint
    def perform_task(self, task_type: str, task: str):
        if task_type == TaskType.POW.name:
            pow_task = PowTask.deserialize(task)
            nonce = pow_gpu(pow_task.data, pow_task.difficulty)
            return PowTaskResult(pow_task, nonce).serialize()
        else:
            return "Invalid Task"


if __name__ == "__main__":
    from communex.module.server import ModuleServer
    import uvicorn

    key = generate_keypair()
    miner = Miner()
    refill_rate = 1 / 400
    # Implementing custom limit
    bucket = TokenBucketLimiter(2, refill_rate)
    server = ModuleServer(miner, key, ip_limiter=bucket,
                          subnets_whitelist=[48])
    app = server.get_fastapi_app()

    # Only allow local connections
    uvicorn.run(app, host="127.0.0.1", port=8000)
