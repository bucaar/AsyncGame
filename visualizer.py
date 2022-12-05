import pygame
import logging

class Visualizer:
    def __init__(self, game_name: str) -> None:
        logging.debug("GAME VISUALIZER: init pygame")
        pygame.init()
        pygame.display.set_caption(game_name)
        self.surface = pygame.display.set_mode((600, 400))
        self.clock = pygame.time.Clock()
        self.running = True
        self.game_name = game_name

    async def setup_visualizer(self) -> None:
        pass

    async def visualize(self, data: str, keyframe: bool) -> int:
        raise NotImplementedError("visualize needs to be implemented")

    async def process_events(self) -> None:
        py_events = pygame.event.get()
        for event in py_events:
            if event.type == pygame.QUIT:
                logging.debug("GAME VISUALIZER: quit event")
                self.running = False

            await self.handle_event(event)

        if not self.running:
            logging.info("GAME VISUALIZER: quit pygame")
            pygame.quit()

    async def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def get_fps(self) -> int:
        return 30