"""
GPU Task Validator Module

This module provides an example GPUTaskValidator class for validating gpu task executed by modules in a subnet.
The GPUTaskValidator retrieves module addresses from the subnet, prompts the modules to execute GPU tasks,
and scores the execution result.

Classes:
    GPUTaskValidator: A class for validating gpu task executed by modules in a subnet.

Functions:
    set_weights: Blockchain call to set weights for miners based on their scores.
    cut_to_max_allowed_weights: Cut the scores to the maximum allowed weights.
    extract_address: Extract an address from a string.
    get_subnet_netuid: Retrieve the network UID of the subnet.
    get_ip_port: Get the IP and port information from module addresses.

Constants:
    IP_REGEX: A regular expression pattern for matching IP addresses.
"""

import asyncio
import concurrent.futures
import re
import time
from functools import partial
import random
import string

from communex.client import CommuneClient
from communex.module.client import ModuleClient
from communex.module.module import Module
from communex.types import Ss58Address
from substrateinterface import Keypair  # type: ignore

from ..tasks.pow import validate_pow
from ..tasks.tasks import PowTask, PowTaskResult, Task, TaskResult, TaskType  # type: ignore

from ._config import ValidatorSettings
from ..utils import log

IP_REGEX = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+")


def set_weights(
    settings: ValidatorSettings,
    score_dict: dict[
        int, float
    ],  # implemented as a float score from 0 to 1, one being the best
    # you can implement your custom logic for scoring
    netuid: int,
    client: CommuneClient,
    key: Keypair,
) -> None:
    """
    Set weights for miners based on their scores.

    Args:
        score_dict: A dictionary mapping miner UIDs to their scores.
        netuid: The network UID.
        client: The CommuneX client.
        key: The keypair for signing transactions.
    """

    # you can replace with `max_allowed_weights` with the amount your subnet allows
    score_dict = cut_to_max_allowed_weights(
        score_dict, settings.max_allowed_weights)

    # Create a new dictionary to store the weighted scores
    weighted_scores: dict[int, int] = {}

    # Calculate the sum of all inverted scores
    scores = sum(score_dict.values())

    # process the scores into weights of type dict[int, int]
    # Iterate over the items in the score_dict
    for uid, score in score_dict.items():
        # Calculate the normalized weight as an integer
        weight = int(score * 1000 / scores)

        # Add the weighted score to the new dictionary
        weighted_scores[uid] = weight

    # filter out 0 weights
    weighted_scores = {k: v for k, v in weighted_scores.items() if v != 0}

    uids = list(weighted_scores.keys())
    weights = list(weighted_scores.values())
    # send the blockchain call
    client.vote(key=key, uids=uids, weights=weights, netuid=netuid)


def cut_to_max_allowed_weights(
    score_dict: dict[int, float], max_allowed_weights: int
) -> dict[int, float]:
    """
    Cut the scores to the maximum allowed weights.

    Args:
        score_dict: A dictionary mapping miner UIDs to their scores.
        max_allowed_weights: The maximum allowed weights (default: 420).

    Returns:
        A dictionary mapping miner UIDs to their scores, where the scores have been cut to the maximum allowed weights.
    """
    # sort the score by highest to lowest
    sorted_scores = sorted(
        score_dict.items(), key=lambda x: x[1], reverse=True)

    # cut to max_allowed_weights
    cut_scores = sorted_scores[:max_allowed_weights]

    return dict(cut_scores)


def extract_address(string: str):
    """
    Extracts an address from a string.
    """
    return re.search(IP_REGEX, string)


def get_subnet_netuid(client: CommuneClient, subnet_name: str = "ccs"):
    """
    Retrieve the network UID of the subnet.

    Args:
        client: The CommuneX client.
        subnet_name: The name of the subnet (default: "foo").

    Returns:
        The network UID of the subnet.

    Raises:
        ValueError: If the subnet is not found.
    """

    subnets = client.query_map_subnet_names()
    for netuid, name in subnets.items():
        if name == subnet_name:
            return netuid
    raise ValueError(f"Subnet {subnet_name} not found")


def get_ip_port(modules_adresses: dict[int, str]):
    """
    Get the IP and port information from module addresses.

    Args:
        modules_addresses: A dictionary mapping module IDs to their addresses.

    Returns:
        A dictionary mapping module IDs to their IP and port information.
    """

    filtered_addr = {id: extract_address(addr)
                     for id, addr in modules_adresses.items()}
    ip_port = {
        id: x.group(0).split(":") for id, x in filtered_addr.items() if x is not None
    }
    return ip_port


class GPUTaskValidator(Module):
    """
    A class for validating gpu task executed by modules in a subnet.

    Attributes:
        client: The CommuneClient instance used to interact with the subnet.
        key: The keypair used for authentication.
        netuid: The unique identifier of the subnet.
        call_timeout: The timeout value for module calls in seconds (default: 60).

    Methods:
        get_modules: Retrieve all module addresses from the subnet.
        _get_miner_task_result: Prompt a miner module to execute the given task.
        _score_miner: Score the execution result.
        get_miner_task: Generate a task for the miner modules.
        validate_step: Perform a validation step by generating task, prompting modules, and scoring results.
        validation_loop: Run the validation loop continuously based on the provided settings.
    """

    def __init__(
        self,
        key: Keypair,
        netuid: int,
        client: CommuneClient,
        call_timeout: int = 60,
    ) -> None:
        super().__init__()
        self.client = client
        self.key = key
        self.netuid = netuid
        self.call_timeout = call_timeout

    def get_addresses(self, client: CommuneClient, netuid: int) -> dict[int, str]:
        """
        Retrieve all module addresses from the subnet.

        Args:
            client: The CommuneClient instance used to query the subnet.
            netuid: The unique identifier of the subnet.

        Returns:
            A dictionary mapping module IDs to their addresses.
        """

        # Makes a blockchain query for the miner addresses
        module_addreses = client.query_map_address(netuid)
        return module_addreses

    def _get_miner_task_result(
        self,
        task: Task,
        miner_info: tuple[list[str], Ss58Address],
    ) -> TaskResult | None:
        """
        Prompt a miner module to execute given task.

        Args:
            task: The serialized task to ask the miner module to execute.
            miner_info: A tuple containing the miner's connection information and key.

        Returns:
            The execution result from the miner module, or None if the miner fails.
        """
        connection, miner_key = miner_info
        module_ip, module_port = connection
        client = ModuleClient(module_ip, int(module_port), self.key)
        try:
            # handles the communication with the miner
            miner_response = asyncio.run(
                client.call(
                    "perform_task",
                    miner_key,
                    {"task_type": task.task_type.name, "task": task.serialize()},
                    timeout=self.call_timeout,  #  type: ignore
                )
            )

            miner_result = None
            if task.task_type == TaskType.POW:
                miner_result = PowTaskResult.deserialize(miner_response)

        except Exception as e:
            log(f"Miner {module_ip}:{
                module_port} failed to generate an result")
            print(e)
            miner_result = None

        return miner_result

    def _score_miner(self, miner_result: TaskResult | None) -> float:
        """
        Validate and score the miner

        Args:
            miner_result: The result of the task from the miner module.

        Returns:
            The score assigned to the miner's result.
        """

        # Implement your custom scoring logic here
        if not miner_result or not self._validate_pow_task_result(miner_result):
            return 0

        # TODO: score based on response time
        return 1

    def _validate_pow_task_result(result: PowTaskResult) -> bool:
        return validate_pow(result)

    def get_miner_task(self, task_type=TaskType.POW) -> Task:
        """
        Generate a gpu based task for the miner modules.

        Returns:
            The generated task for the miner modules.
        """
        default_task = self._get_miner_pow_task()
        if task_type == TaskType.POW:
            return default_task

        return default_task

    def _get_miner_pow_task(self) -> PowTask:
        pow_task_space = string.ascii_letters + string.digits + string.punctuation

        difficulty = 4 * 4  # First 2 bytes unset
        data = ''.join(random.choice(pow_task_space) for _ in range(1))
        return PowTask(data, difficulty)

    async def validate_step(
        self, netuid: int, settings: ValidatorSettings
    ) -> None:
        """
        Perform a validation step.

        Args:
            netuid: The network UID of the subnet.
        """

        # retrive the miner information
        modules_adresses = self.get_addresses(self.client, netuid)
        modules_keys = self.client.query_map_key(netuid)
        val_ss58 = self.key.ss58_address
        if val_ss58 not in modules_keys.values():
            raise RuntimeError(
                f"validator key {val_ss58} is not registered in subnet")

        modules_info: dict[int, tuple[list[str], Ss58Address]] = {}

        modules_filtered_address = get_ip_port(modules_adresses)
        for module_id in modules_keys.keys():
            module_addr = modules_filtered_address.get(module_id, None)
            if not module_addr:
                continue
            modules_info[module_id] = (module_addr, modules_keys[module_id])

        score_dict: dict[int, float] = {}

        miner_task = self.get_miner_task()
        get_miner_result = partial(
            self._get_miner_task_result, miner_task)

        log(f"Selected the following miners: {modules_info.keys()}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            it = executor.map(get_miner_result, modules_info.values())
            miner_results = [*it]

        for uid, miner_response in zip(modules_info.keys(), miner_results):
            miner_result = miner_response
            if not miner_result:
                log(f"Skipping miner {uid} that didn't answer")
                continue

            if miner_result.task != miner_task:
                log(f"Skipping miner {uid} answered for wrong task.")
                continue

            score = self._score_miner(miner_result)
            time.sleep(0.5)
            # score has to be lower or eq to 1, as one is the best score, you can implement your custom logic
            assert score <= 1
            score_dict[uid] = score

        if not score_dict:
            log("No miner managed to give a valid answer")
            return None

        # the blockchain call to set the weights
        _ = set_weights(settings, score_dict, self.netuid,
                        self.client, self.key)

    def validation_loop(self, settings: ValidatorSettings) -> None:
        """
        Run the validation loop continuously based on the provided settings.

        Args:
            settings: The validator settings to use for the validation loop.
        """

        while True:
            start_time = time.time()
            _ = asyncio.run(self.validate_step(self.netuid, settings))

            elapsed = time.time() - start_time
            if elapsed < settings.iteration_interval:
                sleep_time = settings.iteration_interval - elapsed
                log(f"Sleeping for {sleep_time}")
                time.sleep(sleep_time)
