import asyncio
import collections
from datetime import datetime
import logging
from game_rps import RockPaperScissorsGame, RockPaperScissorsVisualizer
from server import Server, Connection
from game import Game, GameOverError, PlayerDisconnectedError
from visualizer import Visualizer
import random
import os.path

class GameManager:
    def __init__(self, server: Server, game_type: type[Game], visualizer_type: type[Visualizer]) -> None:
        self.server = server
        self.game_type = game_type
        self.game: Game = None
        self.players: list[Connection] = []
        self.visualizer_type = visualizer_type
        self.visualizer: Visualizer = None
        self.visualize_queue: collections.deque[str] = collections.deque()
        self.game_frame_queue: collections.deque[str] = collections.deque()
        self.visualizer_file_name: str = ""

        self.start_cooldown = 0

    def reset_start_cooldown(self) -> None:
        self.start_cooldown = self.game.start_cooldown()

    async def wait_for_connections(self) -> list[Connection]:
        while True:
            self.handle_connection_queues()

            active_connections = self.server.connections[:]
            names = [c.name for c in active_connections]
            name_string = " ".join(names)
            logging.debug("GAME_MANAGER there are %d/%d active connections: %r" % (
                len(active_connections), 
                self.game.min_connections(), 
                names)
            )
            
            if len(active_connections) < self.game.min_connections():
                self.reset_start_cooldown()
                logging.debug("GAME_MANAGER send waiting frame")
                self.visualize("WAITING %d %s" % (self.game.min_connections(), name_string), False, False)

                await asyncio.sleep(1)
                continue

            if self.start_cooldown > 0:
                logging.info("GAME_MANAGER starting in %d seconds" % self.start_cooldown)
                logging.debug("GAME_MANAGER send countdown frame")
                self.visualize("START_IN %d %s" % (self.start_cooldown, name_string), False, False)
                
                self.start_cooldown -= 1

                await asyncio.sleep(1)
                continue

            logging.debug("GAME_MANAGER send starting frame")
            self.visualize("STARTING %s" % name_string, False, False)

            self.reset_start_cooldown()

            if self.game.max_connections() > 0 and len(active_connections) > self.game.max_connections():
                active_connections = random.sample(active_connections, self.game.max_connections())
            else:
                random.shuffle(active_connections)

            return active_connections

    async def start(self) -> None:
        gm_tasks: list[asyncio.Task] = []

        logging.info("GAME_MANAGER starting server")
        gm_tasks.append(asyncio.create_task(self.server.start_server()))

        logging.info("GAME_MANAGER initializing game")
        self.game = self.game_type(self.game_frame_queue)
        self.game_name = self.game.get_game_name()
    
        logging.debug("GAME_MANAGER create visualizer file")
        self.visualizer_file_name = self.create_visualizer_file()

        logging.info("GAME_MANAGER initializing visualizer")
        self.visualizer = self.visualizer_type(self.game_name)
        await self.visualizer.setup_visualizer()
        gm_tasks.append(asyncio.create_task(self.visualizer_loop()))

        logging.info("GAME_MANAGER starting game loop")
        gm_tasks.append(asyncio.create_task(self.game_loop()))

        done, pending = await asyncio.wait(gm_tasks, return_when=asyncio.FIRST_COMPLETED)

        logging.info("GAME_MANAGER check for task errors")
        for done_task in done:
            try:
                task_result = done_task.result()
                logging.info("GAME_MANAGER task finished successfully %s" % done_task)
            except Exception as ex:
                logging.error("GAME_MANAGER ERROR task error", exc_info=ex)

        for pending_task in pending:
            logging.info("GAME_MANAGER task pending %s - cancel" % pending_task)
            pending_task.cancel()

        if pending:
            logging.info("GAME_MANAGER wait for pending tasks to fully shut down")
            try:
                await asyncio.wait_for(asyncio.gather(*pending), 10)
                logging.info("GAME_MANAGER pending tasks shut down successfully")
            except Exception as ex:
                logging.error("GAME_MANAGER ERROR pending tasks could not be shut down", exc_info=ex)
        else:
            logging.info("GAME_MANAGER there are no pending tasks")

        logging.info("GAME_MANAGER stop")

    async def game_loop(self) -> None:
        try:
            while True:
                logging.info("GAME_MANAGER wait for connections")
                self.players = await self.wait_for_connections()
                if self.players is None:
                    raise RuntimeError("Connections returned None")
                
                logging.info("GAME_MANAGER play game")
                await self.play_game()

                self.game = None
                self.players = []

                logging.info("GAME_MANAGER initializing new game")
                if self.game_frame_queue:
                    raise RuntimeError("Game frame queue was not empty before initializing the new game")
                
                self.game = self.game_type(self.game_frame_queue)
                game_name = self.game.get_game_name()
                if self.game_name != game_name:
                    raise RuntimeError("Game cannot change names. Original: %s, New: %s" % (self.game_name, game_name))
    
                logging.debug("GAME_MANAGER create new visualizer file")
                self.visualizer_file_name = self.create_visualizer_file()
                
        except asyncio.CancelledError as ex:
            logging.warning("GAME_MANAGER ERROR game loop cancelled", exc_info=ex)

    def handle_connection_queues(self) -> None:
        while self.server.connection_queue:
            connection = self.server.connection_queue.popleft()
            self.reset_start_cooldown()

        while self.server.disconnection_queue:
            connection = self.server.disconnection_queue.popleft()
            self.reset_start_cooldown()

            if self.game is not None and connection in self.players:
                raise PlayerDisconnectedError("Player %s disconnected during game" % connection.name)

    async def play_game(self) -> None:
        try:
            logging.debug("GAME_MANAGER setup game")
            self.game.player_count = len(self.players)
            self.game.player_names = [conn.name for conn in self.players]
            await self.game.setup_game()
            self.handle_game_frame_queue()

            round = -1
            while True:
                round += 1
                logging.info("GAME_MANAGER start round %d" % round)

                logging.debug("GAME_MANAGER prepare round %d" % round)
                await self.game.prepare_round(round)
                self.handle_game_frame_queue()

                logging.debug("GAME_MANAGER get player outputs %d" % round)
                player_outputs = await self.get_player_outputs(round)

                logging.debug("GAME_MANAGER handle player outputs %d" % round)
                for index, output in player_outputs:
                    await self.game.handle_player_output(round, index, output)
                    self.handle_game_frame_queue()

                logging.debug("GAME_MANAGER update game %d" % round)
                await self.game.update_game(round)

                logging.debug("GAME_MANAGER get visualizer data %d" % round)
                await self.visualize_round()

        except PlayerDisconnectedError as ex:
            logging.warning("GAME_MANAGER PlayerDisconnectedError", exc_info=ex)

        except GameOverError as ex:
            logging.warning("GAME_MANAGER GameOverError", exc_info=ex)

        logging.debug("GAME_MANAGER get visualizer data end")
        await self.visualize_round()

        await self.game.on_game_over()
        self.handle_game_frame_queue()

    def create_visualizer_file(self) -> str:
        today = datetime.now()
        date_string = today.strftime("%Y-%m-%d %H:%M:%S")
        base_name = "games/game_%s_%s" % (self.game.get_game_name(), date_string)
        
        duplicate_index = 0
        file_name = "%s.txt" % base_name
        while os.path.isfile(file_name):
            duplicate_index += 1
            file_name = "%s_%d.txt" % (base_name, duplicate_index)

        visualize_file_name = file_name
        with open(visualize_file_name, "w"):
            pass

        return visualize_file_name

    def handle_game_frame_queue(self) -> None:
        while self.game_frame_queue:
            game_frame = self.game_frame_queue.popleft()
            self.visualize(game_frame, False)

    async def visualize_round(self) -> None:
        self.handle_game_frame_queue()

        visualizer_data = self.game.get_visualizer_data()
        if visualizer_data:
            self.visualize(visualizer_data, True)

    def visualize(self, data: str, keyframe: bool, write_to_file: bool = True) -> None:
        for index, conn in enumerate(self.players):
            data = data.replace("@p%d!" % index, conn.name)
        
        if keyframe:
            data = "KEYFRAME " + data
        else:
            data = "FRAME " + data

        self.visualize_queue.append(data)

        if write_to_file:
            with open(self.visualizer_file_name, "a") as file:
                file.write(data)
                file.write("\n")

    async def visualizer_loop(self) -> None:
        try:
            delay = 0
            while True:
                if self.visualizer is None:
                    logging.info("GAME_MANAGER visualizer is None, exit loop")
                    return
                
                await self.visualizer.process_events()
                if not self.visualizer.running:
                    logging.info("GAME_MANAGER visualizer is no longer running, exit loop")
                    self.visualizer = None
                    return

                dt = self.visualizer.clock.tick(self.visualizer.get_fps())
                delay -= dt
                if delay < 0:
                    delay = 0
                
                if delay:
                    await asyncio.sleep(0)
                    continue

                if not self.visualize_queue:
                    await asyncio.sleep(0)
                    continue

                skipped = 0
                data = ""
                while self.visualize_queue and delay == 0:
                    if skipped:
                        logging.info("GAME_MANAGER visualizer skipped frame %d - %s" % (skipped, data))
                    
                    data = self.visualize_queue.popleft()

                    keyframe = False
                    if data.startswith("KEYFRAME "):
                        keyframe = True
                        data = data[9:]
                    elif data.startswith("FRAME "):
                        data = data[6:]
                    else:
                        raise RuntimeError("Unhandled visualize message prefix: %s" % data)
                        
                    delay = await self.visualizer.visualize(data, keyframe)
                    skipped += 1

        except KeyboardInterrupt as ex:
            logging.warning("GAME_MANAGER ERROR visualizer keyboard interrupt", exc_info=ex)
        except asyncio.CancelledError as ex:
            logging.warning("GAME_MANAGER ERROR visualizer cancelled", exc_info=ex)

    async def get_player_outputs(self, round: int) -> list[tuple[int, str]]:
        response_tasks: list[asyncio.Task] = []
        response_indicies: list[int] = []
        task_map: dict[asyncio.Task, int] = {}

        for index, connection in enumerate(self.players):
            round_input = await self.game.get_player_input(round, index)
            self.handle_game_frame_queue()

            if not round_input:
                continue

            response_task = asyncio.create_task(
                self.server.get_response(connection, round_input)
            )

            response_tasks.append(response_task)
            response_indicies.append(index)
            task_map[response_task] = index

        if not response_tasks:
            raise RuntimeError("No player inputs were returned")

        responses: list[str] = [None for _ in response_tasks]
        responded = 0
        expected = len(response_tasks)
        while response_tasks:
            done, response_tasks = await asyncio.wait(response_tasks, return_when=asyncio.FIRST_COMPLETED)

            for response in done:
                responded += 1

                index = task_map[response]
                result: str = response.result()
                responses[index] = result

                logging.debug("GAME_MANAGER response from %d on round %d: %r" % (index, round, result))
                await self.game.on_player_output(round, index, result)
                self.handle_game_frame_queue()

        if responded != expected:
            raise RuntimeError("Did not get all responses on round %d. Expected %d. Recieved %d" % (round, expected, responded))

        self.handle_connection_queues()
        return list(zip(response_indicies, responses))

def main() -> None:
    server = Server()
    gm = GameManager(server, RockPaperScissorsGame, RockPaperScissorsVisualizer)

    asyncio.run(gm.start())

if __name__ == "__main__":
    today = datetime.now()
    date_string = today.strftime("%Y-%m-%d %H:%M:%S")
    logging.basicConfig(filename="log/game %s.log" % date_string, encoding="utf-8", level=logging.INFO)
    # logging.basicConfig(filename="log/game %s.log" % date_string, encoding="utf-8", level=logging.DEBUG)
    # logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)

    try:
        main()
    except Exception as ex:
        logging.critical("GAME_MANAGER ERROR fatal error", exc_info=ex)