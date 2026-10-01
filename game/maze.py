import random
from collections import deque

CELL = 40  # cell size in pixels

def generate_maze(cols, rows):
    """Recursive backtracker maze generation. Returns 2D grid of walls."""
    visited = [[False]*cols for _ in range(rows)]
    # walls: each cell has [N, S, E, W]
    walls = [[[True,True,True,True] for _ in range(cols)] for _ in range(rows)]
    
    def neighbors(r, c):
        dirs = [(-1,0,0,1),(1,0,1,0),(0,1,2,3),(0,-1,3,2)]  # dr,dc,wall_dir,opp_dir
        result = []
        for dr,dc,wd,od in dirs:
            nr,nc = r+dr,c+dc
            if 0<=nr<rows and 0<=nc<cols and not visited[nr][nc]:
                result.append((nr,nc,wd,od))
        return result

    stack = [(0,0)]
    visited[0][0] = True
    while stack:
        r,c = stack[-1]
        nbrs = neighbors(r,c)
        if nbrs:
            nr,nc,wd,od = random.choice(nbrs)
            walls[r][c][wd] = False
            walls[nr][nc][od] = False
            visited[nr][nc] = True
            stack.append((nr,nc))
        else:
            stack.pop()
    return walls

def solve_maze(walls, start, goal):
    """BFS shortest path. start and goal are (row, col) tuples.
    Returns a list of (row, col) cells from start to goal, or [] if no path."""
    rows, cols = len(walls), len(walls[0])
    # (dr, dc, wall_index) -> wall_index matches the [N, S, E, W] layout
    moves = [(-1, 0, 0), (1, 0, 1), (0, 1, 2), (0, -1, 3)]

    queue = deque([start])
    came_from = {start: None}  # cell -> the cell we reached it from

    while queue:
        r, c = queue.popleft()
        if (r, c) == goal:
            break
        for dr, dc, wall_idx in moves:
            nr, nc = r + dr, c + dc
            in_bounds = 0 <= nr < rows and 0 <= nc < cols
            # Only step if there is no wall on that side and the cell is new
            if in_bounds and not walls[r][c][wall_idx] and (nr, nc) not in came_from:
                came_from[(nr, nc)] = (r, c)
                queue.append((nr, nc))

    if goal not in came_from:
        return []

    # Walk backwards from the goal to the start, then reverse
    path = []
    cell = goal
    while cell is not None:
        path.append(cell)
        cell = came_from[cell]
    path.reverse()
    return path

def cell_rect(r, c, import_pygame=None):
    import pygame
    return pygame.Rect(c*CELL, r*CELL, CELL, CELL)
