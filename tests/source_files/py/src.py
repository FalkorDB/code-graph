from typing import Self

def log(msg: str) -> None:
    print(f'msg: {msg}')

class Task():
    def __init__(self, name: str, duration: int):
        self.name = name
        self.duration = duration
        print(f'name: {name}, duration: {duration}')

    def abort(self, delay:float) -> Self:
        log(f'Task {self} aborted')
        return self

