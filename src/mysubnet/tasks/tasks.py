from enum import Enum
import json


class TaskType(Enum):
    POW = 1


class Task:
    def __init__(self, task_type=TaskType.POW):
        self.task_type = task_type

    def serialize(self) -> str:
        raise NotImplemented

    @classmethod
    def deserialize(cls, serialized: str):
        return cls()


class PowTask(Task):
    def __init__(self, data: str, difficulty: int):
        super().__init__(TaskType.POW)
        self.data = data
        self.difficulty = difficulty

    def serialize(self):
        return json.dumps({"data": self.data, "difficulty": self.difficulty})

    @classmethod
    def deserialize(cls, serialized: str):
        task = json.loads(serialized)

        return cls(task["data"], task["difficulty"])

    def __ne__(self, other):
        if not isinstance(other, PowTask):
            return True
        return self.data != other.data or self.difficulty != other.difficulty


class TaskResult:
    def __init__(self, task: Task):
        self.task = task

    def serialize(self) -> str:
        raise NotImplemented

    @classmethod
    def deserialize(cls, serialized: str):
        return cls()


class PowTaskResult(TaskResult):
    def __init__(self, task: PowTask, nonce: int):
        super().__init__(TaskType.POW)
        self.task = task
        self.nonce = nonce

    def serialize(self):
        return json.dumps({"task": self.task.serialize(), "nonce": self.nonce})

    @classmethod
    def deserialize(cls, serialized: str):
        task_result = json.loads(serialized)
        task = PowTask.deserialize(task_result["task"])

        return cls(task, task_result["nonce"])
