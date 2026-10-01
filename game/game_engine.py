import json
import os
import pygame
import time
from game.maze import generate_maze, solve_maze, cell_rect, CELL
from game.player import Player

FPS = 60
BG = (240, 235, 220)
WALL_COLOR = (40, 40, 60)
EXIT_COLOR = (80, 200, 80)
PATH_COLOR = (255, 200, 60)
FOG_COLOR = (10, 10, 20, 255)  # near-black, fully opaque outside the circle
FOG_RADIUS_CELLS = 3           # visible radius, measured in cells
HUD_H = 60                     # height of the bar under the maze

# Difficulty tiers: (name, cols, rows)
DIFFICULTIES = [("Easy", 10, 8), ("Medium", 15, 13), ("Hard", 20, 18)]

# The menu window is the size of the old fixed game window (Medium)
MENU_W = 15 * CELL
MENU_H = 13 * CELL + HUD_H
BUTTON_COLOR = (60, 120, 220)
BUTTON_HOVER = (90, 150, 250)

# leaderboard.json lives in the project root (the folder that contains main.py and game/)
LEADERBOARD_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "leaderboard.json"
)
MAX_ENTRIES = 5


def _clean_times(values):
    """Keep only real positive numbers, sorted fastest first, max 5. Anything else -> []."""
    if not isinstance(values, list):
        return []
    # bool is a number in Python, so exclude it explicitly
    times = [t for t in values
             if isinstance(t, (int, float)) and not isinstance(t, bool) and 0 < t < float("inf")]
    return sorted(times)[:MAX_ENTRIES]


def load_leaderboards():
    """Return {difficulty name: sorted list of up to 5 times}.
    A missing, empty or malformed file gives empty lists instead of crashing."""
    boards = {name: [] for name, _, _ in DIFFICULTIES}
    try:
        with open(LEADERBOARD_FILE, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):  # no file / unreadable / invalid JSON
        return boards
    if isinstance(data, list):
        # Old Task 3 format: one flat list, recorded when only the 15x13 maze existed
        boards["Medium"] = _clean_times(data)
    elif isinstance(data, dict):
        for name in boards:
            boards[name] = _clean_times(data.get(name))
    return boards


def save_leaderboards(boards):
    """Write all leaderboards to leaderboard.json. Never crashes the game if writing fails."""
    try:
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump(boards, f, indent=2)
    except OSError:
        pass


class GameEngine:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((MENU_W, MENU_H))
        pygame.display.set_caption("Maze Runner")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("monospace", 22)
        self.small_font = pygame.font.SysFont("monospace", 16)
        self.big_font = pygame.font.SysFont("monospace", 36, bold=True)
        self.state = "menu"          # "menu" = choosing difficulty, "playing" = in a maze
        self.difficulty_name = None
        self.fog = None              # created in start_game() once the maze size is known
        self.buttons = self.make_buttons()

    # ---------- difficulty menu ----------

    def make_buttons(self):
        """One (rect, difficulty) pair per tier, stacked in the middle of the menu."""
        btn_w, btn_h, gap = 300, 70, 25
        x = MENU_W // 2 - btn_w // 2
        y0 = 220
        return [(pygame.Rect(x, y0 + i * (btn_h + gap), btn_w, btn_h), diff)
                for i, diff in enumerate(DIFFICULTIES)]

    def click_menu(self, pos):
        """Start the game with the difficulty whose button was clicked."""
        for rect, diff in self.buttons:
            if rect.collidepoint(pos):
                self.start_game(diff)
                break

    def start_game(self, difficulty):
        """Apply a difficulty: set maze size, resize window and fog, then build the first maze."""
        self.difficulty_name, self.cols, self.rows = difficulty
        self.width = self.cols * CELL
        self.maze_h = self.rows * CELL
        self.screen = pygame.display.set_mode((self.width, self.maze_h + HUD_H))
        self.fog = pygame.Surface((self.width, self.maze_h), pygame.SRCALPHA)
        self.state = "playing"
        self.reset()

    def draw_menu(self):
        self.screen.fill(BG)
        title = self.big_font.render("Maze Runner", True, WALL_COLOR)
        self.screen.blit(title, (MENU_W // 2 - title.get_width() // 2, 90))
        sub = self.font.render("Choose a difficulty", True, WALL_COLOR)
        self.screen.blit(sub, (MENU_W // 2 - sub.get_width() // 2, 150))

        mouse = pygame.mouse.get_pos()
        for rect, (name, cols, rows) in self.buttons:
            color = BUTTON_HOVER if rect.collidepoint(mouse) else BUTTON_COLOR  # hover highlight
            pygame.draw.rect(self.screen, color, rect, border_radius=8)
            label = self.font.render(f"{name}  ({cols}x{rows})", True, (255, 255, 255))
            self.screen.blit(label, (rect.centerx - label.get_width() // 2,
                                     rect.centery - label.get_height() // 2))
        pygame.display.flip()

    # ---------- game ----------

    def reset(self):
        """Fresh maze at the CURRENT difficulty (self.cols / self.rows are kept)."""
        self.walls = generate_maze(self.cols, self.rows)
        self.player = Player(0, 0)
        self.exit_rect = pygame.Rect((self.cols-1)*CELL+5, (self.rows-1)*CELL+5, CELL-10, CELL-10)
        self.start_time = time.time()  # timer starts fresh with every new maze
        self.elapsed = 0
        self.won = False
        # Leaderboard state for this run
        self.leaderboard = []   # top times for this difficulty, shown on the win screen
        self.rank = None        # position of this run in the leaderboard (None = didn't place)
        # Path hint state (cleared so an old path never carries into a new maze)
        self.show_path = False
        self.path = []
        self.path_start = None  # player cell the cached path was computed from

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if self.state == "menu":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # left click
                    self.click_menu(event.pos)
                continue  # R and H do nothing on the menu
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                self.reset()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_h:
                self.show_path = not self.show_path  # H toggles the hint
                if self.show_path:
                    self.refresh_path()
        return True

    def player_cell(self):
        """Grid cell (row, col) the centre of the player is currently in."""
        r = min(max(self.player.rect.centery // CELL, 0), self.rows - 1)
        c = min(max(self.player.rect.centerx // CELL, 0), self.cols - 1)
        return (r, c)

    def refresh_path(self):
        """Recompute the BFS path only when the player has entered a new cell."""
        cell = self.player_cell()
        if cell != self.path_start:
            self.path_start = cell
            self.path = solve_maze(self.walls, cell, (self.rows-1, self.cols-1))

    def record_win(self):
        """Called once when the exit is reached: add this time to this difficulty's top 5."""
        finish = round(self.elapsed, 2)
        boards = load_leaderboards()  # re-read the file so other difficulties are preserved
        times = boards[self.difficulty_name]
        times.append(finish)
        times.sort()                  # ascending: fastest first
        boards[self.difficulty_name] = times[:MAX_ENTRIES]
        self.leaderboard = boards[self.difficulty_name]
        self.rank = self.leaderboard.index(finish) if finish in self.leaderboard else None
        save_leaderboards(boards)

    def update(self):
        if self.state != "playing" or self.won:
            return  # nothing to update on the menu; timer is frozen after a win
        keys = pygame.key.get_pressed()
        self.player.move(keys, self.walls, self.rows, self.cols)
        self.elapsed = time.time() - self.start_time
        if self.show_path:
            self.refresh_path()
        if self.player.rect.colliderect(self.exit_rect):
            self.won = True
            self.record_win()

    def draw_path(self):
        # Coloured square inside each cell of the shortest path
        for r, c in self.path:
            pygame.draw.rect(self.screen, PATH_COLOR, cell_rect(r, c).inflate(-16, -16), border_radius=4)

    def draw_fog(self):
        """Cover the maze in darkness, then punch a transparent circle around the player."""
        self.fog.fill(FOG_COLOR)
        radius = FOG_RADIUS_CELLS * CELL
        # Alpha 0 on an SRCALPHA surface overwrites the pixels, making them see-through
        pygame.draw.circle(self.fog, (0, 0, 0, 0), self.player.rect.center, radius)
        self.screen.blit(self.fog, (0, 0))

    def draw_maze(self):
        wall_w = 3
        for r in range(self.rows):
            for c in range(self.cols):
                x, y = c*CELL, r*CELL
                w = self.walls[r][c]
                if w[0]: pygame.draw.line(self.screen, WALL_COLOR, (x,y), (x+CELL,y), wall_w)
                if w[1]: pygame.draw.line(self.screen, WALL_COLOR, (x,y+CELL), (x+CELL,y+CELL), wall_w)
                if w[2]: pygame.draw.line(self.screen, WALL_COLOR, (x+CELL,y), (x+CELL,y+CELL), wall_w)
                if w[3]: pygame.draw.line(self.screen, WALL_COLOR, (x,y), (x,y+CELL), wall_w)

    def draw_win_screen(self):
        """Dark overlay, finishing time, top-5 leaderboard and restart hint."""
        overlay = pygame.Surface((self.width, self.maze_h), pygame.SRCALPHA)
        overlay.fill((0,0,0,120))
        self.screen.blit(overlay, (0,0))

        top = self.maze_h//2 - 140  # everything below is positioned relative to this
        msg = self.big_font.render(f"Solved in {self.elapsed:.1f}s!", True, (80,240,80))
        self.screen.blit(msg, (self.width//2 - msg.get_width()//2, top))

        header = self.font.render(f"Top 5 Times ({self.difficulty_name})", True, (255,220,100))
        self.screen.blit(header, (self.width//2 - header.get_width()//2, top + 55))

        for i, t in enumerate(self.leaderboard):
            is_this_run = (i == self.rank)
            color = (80,240,80) if is_this_run else (200,200,200)
            label = f"{i+1}. {t:.2f}s" + ("  <- you" if is_this_run else "")
            row = self.font.render(label, True, color)
            self.screen.blit(row, (self.width//2 - row.get_width()//2, top + 90 + i*28))

        sub = self.font.render("Press R for a new maze", True, (200,200,200))
        self.screen.blit(sub, (self.width//2 - sub.get_width()//2, top + 90 + MAX_ENTRIES*28 + 15))

    def draw(self):
        if self.state == "menu":
            self.draw_menu()
            return
        self.screen.fill(BG)
        if self.show_path:
            self.draw_path()  # under the walls, exit and player
        self.draw_maze()
        pygame.draw.rect(self.screen, EXIT_COLOR, self.exit_rect, border_radius=4)
        ex_label = self.font.render("EXIT", True, (20,80,20))
        self.screen.blit(ex_label, (self.exit_rect.x+2, self.exit_rect.y+4))
        self.player.draw(self.screen)
        self.draw_fog()  # fog goes over the whole maze, but under the HUD and win overlay

        # HUD on two lines so it fits even in the 400 px wide Easy window
        hud = pygame.Rect(0, self.maze_h, self.width, HUD_H)
        pygame.draw.rect(self.screen, (30,30,50), hud)
        time_surf = self.font.render(f"{self.difficulty_name}  Time: {self.elapsed:.1f}s", True, (200,200,200))
        self.screen.blit(time_surf, (10, self.maze_h + 8))
        help_surf = self.small_font.render("R = New Maze   H = Hint", True, (160,160,180))
        self.screen.blit(help_surf, (10, self.maze_h + 36))

        if self.won:
            self.draw_win_screen()
        pygame.display.flip()

    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()
