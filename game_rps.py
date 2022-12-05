import asyncio
import json
import logging
from game import Game, GameOverError
from visualizer import Visualizer
import logging
import pygame
# import pprint

class RockPaperScissorsGame(Game):
    def get_game_name(self) -> str:
        return "Rock Paper Scissors"

    async def setup_game(self) -> None:        
        if self.player_count != 2:
            raise RuntimeError("Unexpected player count: %d" % self.player_count)

        self.valid_moves = {
            "Rock": "Scissors",
            "Paper": "Rock",
            "Scissors": "Paper"
        }

        self.scores: list[int] = [0 for _ in range(self.player_count)]
        self.winning_score: int = 3

        self.waiting: list[bool] = [True for _ in range(self.player_count)]
        self.moves: list[str] = [None for _ in range(self.player_count)]
        self.revealed: bool = False

        self.message: str = ""
        self.delay: int = 0

    async def prepare_round(self, round: int) -> str:
        self.waiting = [True for _ in self.moves]
        self.moves = [None for _ in self.moves]
        self.revealed = False

        self.visualize_frame("Waiting for responses", 0)

    async def get_player_input(self, round: int, player_index: int) -> str:
        return "Rock, Paper, or Scissors?"

    async def on_player_output(self, round: int, player_index: int, player_output: str) -> None:
        self.waiting[player_index] = False

        self.visualize_frame("@p%d! Locked in" % player_index, 2000)
        if any(self.waiting):
            self.visualize_frame("Waiting for responses", 0)

    async def handle_player_output(self, round: int, player_index: int, player_output: str) -> None:
        self.moves[player_index] = player_output

    async def update_game(self, round: int) -> None:
        self.revealed = True
        self.visualize_frame("Revealing choices", 2000)

        if self.moves[0] not in self.valid_moves and self.moves[1] not in self.valid_moves:
            self.visualize_frame("@p0! and @p1! both had invalid moves!", 2000)
            raise GameOverError("Both players had an invalid move: %s, %s" % (*self.moves,))
        elif self.moves[0] not in self.valid_moves:
            self.visualize_frame("@p0! had an invalid move!", 2000)
            raise GameOverError("Player %d had an invalid move: %s" % (0, self.moves[0]))
        elif self.moves[1] not in self.valid_moves:
            self.visualize_frame("@p1! had an invalid move!", 2000)
            raise GameOverError("Player %d had an invalid move: %s" % (1, self.moves[1]))

        round_winner = self.get_round_winner()
        result = ""
        if round_winner == -1:
            logging.info("GAME both players picked %s. This round is a draw!" % self.moves[0])
            result = "@p0! and @p1! draw."
        else:
            index = round_winner
            other_index = 1 - index

            logging.info("GAME %s beats %s! Player %d wins this round!" % (self.moves[index], self.moves[other_index], index))
            result = "@p%d!'s %s beats @p%d!'s %s!" % (index, self.moves[index], other_index, self.moves[other_index])
            self.scores[index] += 1            
        
        self.visualize_frame(result, 4000)

        game_winner = self.get_game_winner()
        if game_winner > -1:
            self.visualize_frame("@p%d! wins!" % game_winner, 4000)
            raise GameOverError("Player %d wins" % game_winner)

    async def on_game_over(self) -> None:
        self.visualize_frame("Game over.", 2000)

    def get_visualizer_data(self) -> str:
        data = {
            "message": self.message,
            "names": self.player_names,
            "scores": self.scores,
            "winning_score": self.winning_score,
            "waiting": self.waiting,
            "revealed": self.revealed,
            "moves": self.moves,
            "round_winner": self.get_round_winner(),
            "game_winner": self.get_game_winner(),
            "delay": self.delay
        }

        return json.dumps(data)

    def min_connections(self) -> int:
        return 2

    def max_connections(self) -> int:
        return 2

    def start_cooldown(self) -> int:
        return 1

    def get_round_winner(self) -> int:
        if any(move is None for move in self.moves):
            return -1

        if any(move not in self.valid_moves for move in self.moves):
            return -1
        
        if self.moves[0] == self.moves[1]:
            return -1

        for index in range(2):
            other_index = 1 - index

            if self.valid_moves[self.moves[index]] == self.moves[other_index]:
                return index

        raise RuntimeError("Could not determine round winner. Moves: %s" % self.moves)

    def get_game_winner(self) -> int:
        for index in range(2):
            if self.scores[index] >= self.winning_score:
                return index
        
        return -1

    def visualize_frame(self, message: str, delay: int) -> None:
        self.message = message
        self.delay = delay
        self.visualize()
        self.message = ""
        self.delay = 0

class RockPaperScissorsVisualizer(Visualizer):
    async def setup_visualizer(self) -> None:
        self.font = pygame.font.SysFont("arial", 20)

    async def visualize(self, data: str, keyframe: bool) -> int:
        self.surface.fill((255, 255, 255))

        center_x = self.surface.get_width() // 2
        center_y = self.surface.get_height() // 2

        if data.startswith("WAITING"):
            parameters = data.split()
            required = int(parameters[1])
            names = parameters[2:]

            self.draw_text(self.game_name, center_x, center_y - 25)
            self.draw_text("Waiting to start...", center_x, center_y + 25)
            self.draw_text("%d/%d players connected" % (len(names), required), center_x, center_y + 50)
            self.draw_text("[%s]" % ", ".join(names), center_x, center_y + 75)

            pygame.display.flip()
            return 0

        if data.startswith("START_IN"):
            parameters = data.split()
            countdown = int(parameters[1])
            names = parameters[2:]

            self.draw_text(self.game_name, center_x, center_y - 25)
            self.draw_text("Starting in %d..." % countdown, center_x, center_y + 25)
            self.draw_text("[%s]" % ", ".join(names), center_x, center_y + 50)

            pygame.display.flip()
            return 0

        if data.startswith("STARTING"):
            parameters = data.split()
            names = parameters[1:]

            self.draw_text(self.game_name, center_x, center_y - 25)
            self.draw_text("Starting", center_x, center_y + 25)
            self.draw_text("[%s]" % ", ".join(names), center_x, center_y + 50)

            pygame.display.flip()
            return 0
        
        data = json.loads(data)

        self.draw_text(self.game_name, center_x, 30)
        self.draw_text("%d - %d" % (data["scores"][0], data["scores"][1]), center_x, 55)

        frame_offset_y = 0
        for index in range(2):
            frame_width = 150
            frame_height = 245
            frame_padding = 80

            frame_rect = pygame.rect.Rect(0, 0, frame_width, frame_height)
            frame_rect.center = (center_x, center_y)
            offset_x = (index * 2 - 1) * (frame_width + frame_padding) / 2
            frame_rect.x += offset_x
            frame_rect.y += frame_offset_y

            

            if data["game_winner"] == -1:
                if data["round_winner"] == -1:
                    background_color = (200, 200, 200)
                elif data["round_winner"] == index:
                    background_color = (200, 255, 200)
                else:
                    background_color = (255, 200, 200)
            elif data["game_winner"] == index:
                background_color = (200, 255, 200)
            else:
                background_color = (200, 200, 200)

            pygame.draw.rect(self.surface, background_color, frame_rect, 0, 10)
            pygame.draw.rect(self.surface, (0, 0, 0), frame_rect, 1, 10)

            self.draw_text(data["names"][index], frame_rect.centerx, frame_rect.y + 15)

            choice = ""
            if data["revealed"]:
                choice = data["moves"][index]
            else:
                choice = "Waiting" if data["waiting"][index] else "Ready"
                    
            self.draw_text(choice, frame_rect.centerx, frame_rect.centery)

        self.draw_text("vs.", center_x, center_y + frame_offset_y)

        self.draw_text(data["message"], center_x, 350)

        pygame.display.flip()

        delay = 0
        if keyframe:
            delay = 2000
        delay = max(delay, data["delay"])
        
        return delay

    def draw_text(self, text: str, center_x: int, center_y: int) -> None:
        text_render = self.font.render(text, True, (0, 0, 0))
        text_render_rect = text_render.get_rect()
        text_render_rect.center = (center_x, center_y)

        self.surface.blit(text_render, text_render_rect)