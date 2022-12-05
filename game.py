
import collections

class Game:
    def __init__(self, visualize_queue: collections.deque[str]) -> None:
        self.visualize_queue = visualize_queue
        self.player_count = 0
        self.player_names: list[str] = []

    def get_game_name(self) -> str:
        raise NotImplementedError("get_game_name needs to be implemented")

    async def setup_game(self) -> None:
        pass

    async def prepare_round(self, round: int) -> str:
        return None

    async def get_player_input(self, round: int, player_index: int) -> str:
        raise NotImplementedError("get_player_input needs to be implemented")

    async def on_player_output(self, round: int, player_index: int, player_output: str) -> None:
        pass

    async def handle_player_output(self, round: int, player_index: int, player_output: str) -> None:
        raise NotImplementedError("handle_player_output needs to be implemented")

    async def update_game(self, round: int) -> None:
        raise NotImplementedError("update_game needs to be implemented")

    async def on_game_over(self) -> None:
        pass

    def get_visualizer_data(self) -> str:
        pass

    def visualize(self) -> None:
        data = self.get_visualizer_data()
        if data:
            self.visualize_queue.append(data)

    def min_connections(self) -> int:
        return 1

    def max_connections(self) -> int:
        return 0

    def start_cooldown(self) -> int:
        return 10

class PlayerDisconnectedError(Exception):
    pass

class GameOverError(Exception):
    pass