# game.py
from cmath import rect
import os
import sys
from turtle import title
import pygame
from pygame.locals import *
from piece import Piece
from chess import Chess
import time  

pygame.init()
pygame.mixer.init()
try:
    move_sound = pygame.mixer.Sound("sound/move.wav")
    capture_sound = pygame.mixer.Sound("sound/capture.wav")
    lightning_sound=pygame.mixer.Sound("sound/lightning.mp3")
except Exception as e:
    print("Error loading sound:", e)

# lightning sound for superpower (try mp3 first, fallback to wav)
try:
    lightning_sound = pygame.mixer.Sound("sound/lightning.mp3")
except Exception:
    try:
        lightning_sound = pygame.mixer.Sound("sound/lightning.wav")
    except Exception as e:
        lightning_sound = None
        print("Error loading lightning sound:", e)

# Optional: set volume
move_sound.set_volume(1.0)
capture_sound.set_volume(1.0)
if lightning_sound:
    lightning_sound.set_volume(0.8)


try:
    from superchess import SuperChess
    HAS_SUPER = True
except Exception:
    HAS_SUPER = False

from utils import Utils


# --- Visual HUD: top bar, move history, replay controls, overlays (visual-only) ---
import pygame, time, math, traceback, os, copy

HUD_WIDTH = 360
TOP_BAR = 96
BOARD_MARGIN = 40

BG_COLOR = (24, 24, 24)
BOARD_LIGHT = (246, 246, 238)
BOARD_DARK = (120, 120, 90)
RIGHT_PANEL_BG = (178, 203, 222)
HUD_BG = (18, 18, 18)
TEXT_LIGHT = (245, 245, 245)
PREVIEW_YELLOW = (255, 200, 20, 120)
PREVIEW_RED = (200, 24, 24, 140)
HIGHLIGHT_SRC = (255, 255, 120, 160)
HIGHLIGHT_DST = (120, 255, 160, 160)

def choose_font(name_list, size, bold=False):
    for n in name_list:
        f = pygame.font.match_font(n)
        if f:
            return pygame.font.Font(f, size)
    return pygame.font.SysFont(None, size, bold=bold)

def helvetica(size, bold=False):
    return choose_font(["Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"], size, bold=bold)

def safe_deepcopy(x):
    try:
        return copy.deepcopy(x)
    except Exception:
        return x

class HUD:
    """HUD visual class. Attach to controller (Game) and it will draw right-side HUD,
    move history, small replay controls and handle simple visual interactions.
    It deliberately does NOT contain any gameplay/capture logic.
    """
    def __init__(self, controller, res_dir=None):
        self.controller = controller
        self.width = HUD_WIDTH
        self.res_dir = res_dir or os.path.join(os.path.dirname(__file__), "res")
        # button icons
        self.icon_left = None
        self.icon_right = None
        self.icon_play_pause = None
        try:
            left_path = os.path.join(self.res_dir, "left.png")
            right_path = os.path.join(self.res_dir, "right.png")
            play_pause_path = os.path.join(self.res_dir, "play_pause.png")
            if os.path.exists(left_path):
                self.icon_left = pygame.transform.smoothscale(pygame.image.load(left_path).convert_alpha(), (22,22))
            if os.path.exists(right_path):
                self.icon_right = pygame.transform.smoothscale(pygame.image.load(right_path).convert_alpha(), (22,22))
            if os.path.exists(play_pause_path):
                self.icon_play_pause = pygame.transform.smoothscale(pygame.image.load(play_pause_path).convert_alpha(), (22,22))
        except Exception:
            self.icon_left = self.icon_right = self.icon_play_pause = None

        # fonts
        self.font_title = helvetica(20)
        self.font_small = helvetica(14)
        mono_font = pygame.font.match_font("Consolas") or pygame.font.match_font("Courier New") or pygame.font.match_font("DejaVu Sans Mono")
        if mono_font:
            self.font_mono = pygame.font.Font(mono_font, 14)
        else:
            self.font_mono = pygame.font.SysFont(None, 14)

        # thunder icon
        self.thunder_img = None
        png_path = os.path.join(self.res_dir, "thunder.png")
        if os.path.exists(png_path):
            try:
                img = pygame.image.load(png_path).convert_alpha()
                self.thunder_img = pygame.transform.smoothscale(img, (20,20))
            except Exception:
                self.thunder_img = None
        if self.thunder_img is None:
            glyph_font = helvetica(20, bold=True)
            s = glyph_font.render("⚡", True, (255,210,30))
            surf = pygame.Surface((s.get_width()+6, s.get_height()+6), pygame.SRCALPHA)
            surf.blit(s, (3,3))
            self.thunder_img = surf

        # history / preview state
        self.scroll_offset = 0
        self.selected_idx = None
        self.preview_snapshot = None
        self.preview_active = False
        self.list_rect = None

        # replay/traverse state
        self.replay_mode = False
        self.replay_index = None
        self.replay_playing = False
        self.replay_last_tick = None
        self.replay_interval_ms = 700

        # control rects
        self.btn_step_back = None
        self.btn_play_pause = None
        self.btn_step_forward = None

        # double-click tracking
        self._last_click_idx = -1
        self._last_click_time = 0

    def rect(self, screen_w, screen_h):
        return pygame.Rect(screen_w - self.width, 0, self.width, screen_h)

    def draw(self, surf):
        r = self.rect(self.controller.width, self.controller.height)
        pygame.draw.rect(surf, HUD_BG, r)

        pad = 14
        x = r.x + pad
        y = r.y + pad

        title = "SuperChess" if (getattr(self.controller, "variant", "") == "super") else "Classic"
        surf.blit(self.font_title.render(title, True, TEXT_LIGHT), (x, y))
        y += 34

        # player blocks
        block_h = 44
        engine = getattr(self.controller, "chess", None)
        wc = getattr(self.controller, "current_turn_color", "") == "white"
        bc = getattr(self.controller, "current_turn_color", "") == "black"
        white_charges = 0; black_charges = 0
        try:
            if engine and hasattr(engine, "charges"):
                white_charges = engine.charges.get("white", 0)
                black_charges = engine.charges.get("black", 0)
        except Exception:
            pass

        self._draw_player_block(surf, x, y, r.width - pad*2, getattr(self.controller, "name_white", "White"), wc, white_charges)
        y += block_h + 8
        self._draw_player_block(surf, x, y, r.width - pad*2, getattr(self.controller, "name_black", "Black"), bc, black_charges)
        y += block_h + 12

        # small replay step controls
        step_h = 28
        step_w = (r.width - pad*2 - 16) // 3
        sbx = x; sby = y
        step_back_rect = pygame.Rect(sbx, sby, step_w, step_h)
        play_rect = pygame.Rect(sbx + step_w + 8, sby, step_w, step_h)
        step_forward_rect = pygame.Rect(sbx + 2*(step_w + 8), sby, step_w, step_h)
        play_label = "Pause" if self.replay_playing else "Play"
        self._draw_button(surf, step_back_rect, "", icon=self.icon_left, disabled=(not self._can_replay()))
        self._draw_button(surf, play_rect, "", icon=self.icon_play_pause, disabled=(not self._can_replay()))
        self._draw_button(surf, step_forward_rect, "", icon=self.icon_right, disabled=(not self._can_replay()))
        self.btn_step_back, self.btn_play_pause, self.btn_step_forward = step_back_rect, play_rect, step_forward_rect
        y += step_h + 12

        # divider and "Move History" label
        pygame.draw.line(surf, (60,60,60), (x, y), (r.right - pad, y), 1)
        y += 12
        surf.blit(self.font_small.render("Move History", True, (170,170,170)), (x, y))
        y += 22

        # history list
        list_h = r.bottom - y - 24
        list_rect = pygame.Rect(x, y, r.width - pad*2, list_h)
        pygame.draw.rect(surf, (8,8,8), list_rect)
        self.list_rect = list_rect

        history = getattr(self.controller, "history", []) or []
        total = len(history)
        max_lines = max(1, list_rect.height // 22)
        if total != getattr(self, "_last_history_len", None) and (self.selected_idx is None or self.selected_idx >= total-2):
            self.scroll_offset = max(0, total - max_lines)
        self._last_history_len = total

        visible_start = self.scroll_offset
        visible_end = min(total, visible_start + max_lines)
        ly = list_rect.y + 6
        for i in range(visible_start, visible_end):
            e = history[i]
            num = f"{i+1:3d}."
            san = e.get("san", "?")
            power = e.get("power")
            text = f"{num} {san}" + (f" [{power}]" if power else "")
            if i == self.selected_idx:
                bg = pygame.Surface((list_rect.w - 4, 20))
                bg.fill((50, 50, 50))
                surf.blit(bg, (list_rect.x + 2, ly))
                color = (255, 230, 170)
            else:
                color = (180,180,180)
            surf.blit(self.font_mono.render(text, True, color), (list_rect.x + 8, ly))
            ly += 22

        # scrollbar
        if total > max_lines:
            sb_h = int(max(8, (max_lines / total) * list_rect.height))
            sb_y = list_rect.y + int((self.scroll_offset / max(1, total - max_lines)) * (list_rect.height - sb_h))
            sb_rect = pygame.Rect(list_rect.right - 10, sb_y, 8, sb_h)
            pygame.draw.rect(surf, (90,90,90), sb_rect, border_radius=4)

    def _draw_player_block(self, surf, x, y, w, name, is_turn, charges):
        block_h = 44
        pygame.draw.rect(surf, (30,30,30), (x, y, w, block_h), border_radius=8)
        if is_turn:
            t = time.time(); pulse = (math.sin(t*3)+1)/2; alpha = int(40 + 70*pulse)
            gl = pygame.Surface((w, block_h), pygame.SRCALPHA)
            gl.fill((RIGHT_PANEL_BG[0], RIGHT_PANEL_BG[1], RIGHT_PANEL_BG[2], alpha))
            surf.blit(gl, (x, y))

        # name (left)
        name_surf = self.font_small.render(name, True, TEXT_LIGHT)
        surf.blit(name_surf, (x + 12, y + (block_h - name_surf.get_height())//2))

        # compute timer for this player (visual only)
        color = "white" if name.lower().startswith("w") else "black"
        timer_val = None
        try:
            timer_val = getattr(self.controller, "remaining", {}).get(color)
            # if this player is the live side, account for active elapsed time
            if timer_val is not None and getattr(self.controller, "current_turn_color", "") == color and getattr(self.controller, "turn_start_ticks", None):
                now = pygame.time.get_ticks()
                elapsed = (now - self.controller.turn_start_ticks) / 1000.0
                timer_val = max(0, timer_val - elapsed)
        except Exception:
            timer_val = None

        # format mm:ss or ∞
        if timer_val is None:
            timer_text = "∞"
        else:
            m = int(timer_val) // 60
            s = int(timer_val) % 60
            timer_text = f"{m}:{s:02d}"
        timer_surf = self.font_small.render(timer_text, True, TEXT_LIGHT)

        # draw timer, thunder icon, and charge count on the right — timer is placed left of thunder
        cnt_surf = self.font_small.render(str(charges), True, TEXT_LIGHT)
        thunder_w = self.thunder_img.get_width()
        # right align the charge count at the right edge with some padding
        cnt_x = x + w - 8 - cnt_surf.get_width()
        cnt_y = y + (block_h - cnt_surf.get_height())//2
        thunder_x = cnt_x - 8 - thunder_w
        thunder_y = y + (block_h - self.thunder_img.get_height())//2
        timer_x = thunder_x - 8 - timer_surf.get_width()
        timer_y = y + (block_h - timer_surf.get_height())//2

        # blit in order: timer, thunder, count
        surf.blit(timer_surf, (timer_x, timer_y))
        surf.blit(self.thunder_img, (thunder_x, thunder_y))
        surf.blit(cnt_surf, (cnt_x, cnt_y))


    def _draw_button(self, surf, rect, text, icon=None, disabled=False):
        color = (60,60,60) if not disabled else (40,40,40)
        pygame.draw.rect(surf, color, rect, border_radius=8)
        lab = self.font_small.render(text, True, (220,220,220) if not disabled else (160,160,160))
        # Center icon and text horizontally
        if icon and not text:
            # Center icon horizontally and vertically
            icon_x = rect.x + (rect.width - icon.get_width()) // 2
            icon_y = rect.y + (rect.height - icon.get_height()) // 2
            surf.blit(icon, (icon_x, icon_y))
        elif icon and text:
            # Center icon and text as a group
            total_width = icon.get_width() + 6 + lab.get_width()
            start_x = rect.x + (rect.width - total_width) // 2
            icon_x = start_x
            icon_y = rect.y + (rect.height - icon.get_height()) // 2
            surf.blit(icon, (icon_x, icon_y))
            text_x = icon_x + icon.get_width() + 6
            text_y = rect.y + (rect.height - lab.get_height()) // 2
            surf.blit(lab, (text_x, text_y))
        else:
            # Only text, center horizontally
            text_x = rect.x + (rect.width - lab.get_width()) // 2
            text_y = rect.y + (rect.height - lab.get_height()) // 2
            surf.blit(lab, (text_x, text_y))

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            mx,my = ev.pos
            if self.btn_step_back and self.btn_step_back.collidepoint(mx,my):
                if self._can_replay():
                    self._on_replay_step(-1); return True
            if self.btn_play_pause and self.btn_play_pause.collidepoint(mx,my):
                if self._can_replay():
                    self._on_replay_toggle_play(); return True
            if self.btn_step_forward and self.btn_step_forward.collidepoint(mx,my):
                if self._can_replay():
                    self._on_replay_step(1); return True
            if self.list_rect and self.list_rect.collidepoint(mx,my):
                local_y = my - self.list_rect.y
                idx = self.scroll_offset + (local_y // 22)
                history_len = len(getattr(self.controller, "history", []) or [])
                if 0 <= idx < history_len:
                    now = pygame.time.get_ticks()
                    if getattr(self, "_last_click_idx", -1) == idx and now - getattr(self, "_last_click_time", 0) < 350:
                        self.selected_idx = idx
                        self._on_preview()
                        self._last_click_idx = -1; self._last_click_time = 0
                    else:
                        self.selected_idx = idx; self._last_click_idx = idx; self._last_click_time = now
                return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (4,5):
            mx,my = ev.pos
            if self.list_rect and self.list_rect.collidepoint(mx,my):
                history = getattr(self.controller, "history", []) or []
                max_lines = self.list_rect.height // 22
                max_scroll = max(0, len(history) - max_lines)
                if ev.button == 4:
                    self.scroll_offset = max(0, self.scroll_offset - 1)
                else:
                    self.scroll_offset = min(max_scroll, self.scroll_offset + 1)
                return True
        return False

    def _can_replay(self):
        return self.selected_idx is not None and len(getattr(self.controller, "snapshots", []) or []) > 0

    def _on_preview(self):
        if not self._can_replay(): return
        idx = self.selected_idx
        try:
            self.preview_snapshot = self.controller.snapshot_game_state()
            self.controller.start_replay_preview(idx, destructive=False)
        except Exception:
            traceback.print_exc()
            self.preview_snapshot = None
            return
        self.preview_active = True
        self.replay_mode = True
        self.replay_index = idx
        self.replay_playing = False
        self.replay_last_tick = pygame.time.get_ticks()

    def _on_replay_step(self, delta):
        if not self._can_replay(): return
        if self.replay_index is None:
            self.replay_index = self.selected_idx if self.selected_idx is not None else (len(getattr(self.controller, "history", []) or [])-1 if getattr(self.controller, "history", None) else 0)
        new_idx = max(0, min(len(getattr(self.controller, "history", []) or [])-1, self.replay_index + delta))
        self.replay_index = new_idx
        try:
            self.controller._apply_replay_index_to_preview(new_idx)
        except Exception:
            traceback.print_exc()
        self.selected_idx = new_idx

    def _on_replay_toggle_play(self):
        if not self._can_replay(): return

        # Start playing from the beginning (index 0)
        if not self.replay_playing:
            # set to start
            self.replay_index = 0
            self.selected_idx = 0
            try:
                # apply the initial index immediately to show the first move
                self.controller._apply_replay_index_to_preview(0)
            except Exception:
                traceback.print_exc()
            # mark the time we started
            self.replay_last_tick = pygame.time.get_ticks()
            self.replay_playing = True
        else:
            # turn playback off
            self.replay_playing = False


    def _on_return_live(self):
        if self.preview_snapshot:
            try:
                self.controller.restore_game_state(self.preview_snapshot)
            except Exception:
                traceback.print_exc()
        self.preview_snapshot = None
        self.preview_active = False
        self.replay_mode = False
        self.replay_index = None
        self.replay_playing = False
        self.controller.preview_piece_location = None
        self.selected_idx = None


RES_DIR = os.path.join(os.path.dirname(__file__), "res")

class Game:
    def __init__(self):
        pygame.display.init()
        pygame.font.init()

        self.promotion_overlay = None
        self.promotion_active = False

        info = pygame.display.Info()
        # window slightly smaller than full screen so X remains accessible
        target_w = max(960, int(info.current_w * 0.88))
        target_h = max(700, int(info.current_h * 0.88))
        self.width, self.height = target_w, target_h
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("SuperChess")
        self.clock = pygame.time.Clock()

        self.resources = "res"
        icon_src = os.path.join(self.resources, "chess_icon.png")
        if os.path.exists(icon_src):
            try:
                pygame.display.set_icon(pygame.image.load(icon_src))
            except Exception:
                pass
        
                # --- load menu background ---
        bg_path = os.path.join(RES_DIR, "background.jpg")   # RES_DIR is already defined near top of file
        if os.path.exists(bg_path):
            try:
                img = pygame.image.load(bg_path)
                # preserve alpha if PNG, otherwise convert for speed
                try:
                    img = img.convert_alpha()
                except Exception:
                    img = img.convert()
                self.background = pygame.transform.smoothscale(img, (self.width, self.height))
            except Exception:
                self.background = None
        else:
            self.background = None


        # state
        self.state = "menu"   # menu, name_entry, playing, end
        self.game_mode = None
        self.variant = "classic"
        self.timer_mode = "timeless"

        self.timer_presets = {"bullet": 60, "blitz": 300, "rapid": 600, "classic": 1800, "timeless": None}

        # runtime
        self.chess = None
        self.utils = Utils()

        # layout
        self.square_length = None
        self.TOP_BAR = 96
        self.BOARD_MARGIN = 40

        # load board image
        bsrc = os.path.join(RES_DIR, "board.png")
        self.board_img = pygame.image.load(bsrc).convert() if os.path.exists(bsrc) else None

        # names & timers
        self.name_white = "White"
        self.name_black = "Black (AI)"
        self.remaining = {"white": None, "black": None}
        self.turn_start_ticks = None
        self.current_turn_color = "white"
        #timer will not start until white makes first move
        self.timers_started= False

        # HUD / visual bookkeeping
        self.hud = HUD(self, res_dir=RES_DIR)
        self.history = []
        self.snapshots = []
        self.preview_piece_location = None
        self.preview_highlight_move = None
        self._last_seen_move_id = None
        self.captured_white = []
        self.captured_black = []

        self.show_resign_modal = False

    def start_game(self):
        while True:
            if self.state == "menu":
                self.menu()                 # sets game_mode/variant/timer
                # ask names
                self.name_entry()
                self.start_variant()
                self.state = "playing"
                continue

            if self.state == "playing":
                self.loop_playing()
                if self.state != "playing":
                    continue

            if self.state == "end":
                self.end_screen()
                continue

            self.clock.tick(60)

    # ---------------- Menu ----------------
    def menu(self):
        big = pygame.font.SysFont("comicsansms", 56)
        med = pygame.font.SysFont("comicsansms", 28)
        small = pygame.font.SysFont("comicsansms", 22)

        self.game_mode = None
        self.variant = "classic"
        self.timer_mode = "timeless"

        cx = self.width // 2
        y = 120
        pvp_btn = pygame.Rect(cx - 160, y + 80, 320, 60)
        engine_btn = pygame.Rect(cx - 160, y + 160, 320, 60)
        classic_btn = pygame.Rect(cx - 180, y + 260, 160, 52)
        super_btn = pygame.Rect(cx + 20, y + 260, 160, 52)

        timer_labels = list(self.timer_presets.keys())
        timer_rects = []
        timer_y = y + 340
        tw = 150; spacing = 10
        row_w = len(timer_labels) * tw + (len(timer_labels)-1)*spacing
        start_x = cx - row_w // 2
        for i,label in enumerate(timer_labels):
            timer_rects.append((pygame.Rect(start_x + i*(tw+spacing), timer_y, tw, 48), label))

        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx,my = ev.pos
                    if pvp_btn.collidepoint(mx,my):
                        self.game_mode = "pvp"
                    elif engine_btn.collidepoint(mx,my):
                        self.game_mode = "engine"
                    elif classic_btn.collidepoint(mx,my):
                        self.variant = "classic"
                    elif super_btn.collidepoint(mx,my) and HAS_SUPER:
                        self.variant = "super"
                    for r,label in timer_rects:
                        if r.collidepoint(mx,my):
                            self.timer_mode = label
                    if self.game_mode:
                        return

            if getattr(self, "background", None):
                self.screen.blit(self.background, (0,0))
                # subtle dark dim so buttons/readable
                dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                dim.fill((0,0,0,150))
                self.screen.blit(dim, (0,0))
            else:
                self.screen.fill((245,245,245))
                
            

            # glass panel behind the menu content (adjust x,y,w,h to taste)
            box_w = 850
            box_h = 400
            
            panel_rect = pygame.Rect(self.width// 2 - box_w // 2, y + 2, box_w, box_h)
            self.draw_glass_panel(panel_rect, alpha=80)

            
            title = big.render("SuperChess", True, (12,12,12))
            self.screen.blit(title, (self.width//2 - title.get_width()//2, y))

            def draw_btn(rect, label, selected=False):
                pygame.draw.rect(self.screen, (10,10,10), rect, 0 if selected else 2)
                txt = med.render(label, True, (255,255,255) if selected else (0,0,0))
                self.screen.blit(txt, (rect.centerx - txt.get_width()//2, rect.centery - txt.get_height()//2))

            draw_btn(pvp_btn, "Play vs Player", selected=(self.game_mode=="pvp"))
            draw_btn(engine_btn, "Play vs AI", selected=(self.game_mode=="engine"))
            draw_btn(classic_btn, "Classic", selected=(self.variant=="classic"))
            draw_btn(super_btn, "Super" if HAS_SUPER else "Super (missing)", selected=(self.variant=="super" and HAS_SUPER))

            label = small.render("Timer Mode", True, (40,40,40))
            self.screen.blit(label, (self.width//2 - label.get_width()//2, timer_y-28))
            for r,label in timer_rects:
                draw_btn(r, label.capitalize(), selected=(self.timer_mode==label))

            footer = small.render("Press Esc to quit", True, (80,80,80))
            self.screen.blit(footer, (self.width - footer.get_width() - 10, self.height - footer.get_height() - 6))

            pygame.display.flip()
            self.clock.tick(60)

    # ---------------- Name entry modal ----------------
    def name_entry(self):
        """Modal dialog that asks for White and Black player names. Blocks until finished."""
        font = pygame.font.SysFont("comicsansms", 24)
        box_w = 550; box_h = 280
        box = pygame.Rect(self.width//2 - box_w//2, self.height//2 - box_h//2, box_w, box_h)
        input_white = ""
        input_black = ""
        active = "white"  # 'white' or 'black'
        prompt = "Enter player names (press Enter to continue)"

        # default black name when engine selected
        if self.game_mode == "engine":
            input_black = "AI"

        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    if ev.key == pygame.K_TAB:
                        active = "black" if active == "white" else "white"
                    elif ev.key == pygame.K_RETURN:
                        # accept, but ensure non-empty
                        if input_white.strip() == "":
                            input_white = "White"
                        if input_black.strip() == "":
                            input_black = "Black" if self.game_mode=="pvp" else "AI"
                        self.name_white = input_white.strip()
                        self.name_black = input_black.strip()
                        return
                    elif ev.key == pygame.K_BACKSPACE:
                        if active == "white":
                            input_white = input_white[:-1]
                        else:
                            input_black = input_black[:-1]
                    else:
                        ch = ev.unicode
                        if ch and ord(ch) >= 32:
                            if active == "white":
                                input_white += ch
                            else:
                                input_black += ch
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx,my = ev.pos
                    # click to select input areas
                    wbox = pygame.Rect(box.x+24, box.y+60, box.w-48, 40)
                    bbox = pygame.Rect(box.x+24, box.y+130, box.w-48, 40)
                    if wbox.collidepoint(mx,my): active = "white"
                    elif bbox.collidepoint(mx,my): active = "black"

            # draw modal
            # draw background and modal glass
            if getattr(self, "background", None):
                self.screen.blit(self.background, (0,0))
                dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                dim.fill((0,0,0,150))   # darker dim for modal focus
                self.screen.blit(dim, (0,0))
            else:
                self.screen.fill((230,230,230))

            # draw semi-transparent modal (glass) in place of opaque white box
            glass = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
            glass.fill((255,255,255,100))   # alpha=200 to keep inputs readable; lower for more transparency
            pygame.draw.rect(glass, (255,255,255,30), glass.get_rect(), 1, border_radius=8)
            self.screen.blit(glass, (box.x, box.y))

            title = font.render("Enter Player Names", True, (10, 10, 10))
            self.screen.blit(title, (box.centerx - title.get_width()//2, box.y + 8))

            label_w = font.render("White name:", True, (10,10,10))
            self.screen.blit(label_w, (box.x+24, box.y+55))
            wbox = pygame.Rect(box.x+24, box.y+90, box.w-48, 40)
            pygame.draw.rect(self.screen, (245,245,245), wbox)
            txtw = font.render(input_white if input_white else "White", True, (10,10,10))
            self.screen.blit(txtw, (wbox.x+3, wbox.y+3))
            if active == "white":
                pygame.draw.rect(self.screen, (0,0,0), wbox, 2)

            label_b = font.render("Black name:", True, (10,10,10))
            self.screen.blit(label_b, (box.x+24, box.y+140))
            bbox = pygame.Rect(box.x+24, box.y+175, box.w-48, 40)
            pygame.draw.rect(self.screen, (245,245,245), bbox)
            txtb = font.render(input_black if input_black else ("AI" if self.game_mode=="engine" else "Black"), True, (10,10,10))
            self.screen.blit(txtb, (bbox.x+3, bbox.y+3))
            if active == "black":
                pygame.draw.rect(self.screen, (0,0,0), bbox, 2)

            hint = font.render("Enter: Continue  Tab: Switch input", True, (40,40,40))
            self.screen.blit(hint, (box.centerx - hint.get_width()//2, box.y + box.h - 34))

            pygame.display.flip()
            self.clock.tick(60)

    # ---------------- Setup variant ----------------
    def start_variant(self):
        # compute square size to fit board centered and leave space for top HUD
        usable_h = self.height - self.TOP_BAR - self.BOARD_MARGIN
        usable_w = self.width - 2*self.BOARD_MARGIN
        sq = min(usable_w // 8, usable_h // 8)
        self.square_length = max(28, sq)

        board_size = self.square_length * 8
        bx = BOARD_MARGIN
        by = TOP_BAR
        self.board_top_left = (bx, by)
        self.board_rect = pygame.Rect(bx, by, board_size, board_size)

        panel_x = bx + board_size + 12
        panel_w = self.width - panel_x - BOARD_MARGIN
        panel_h = board_size
        self.right_panel_rect = pygame.Rect(panel_x, by, panel_w, panel_h)

        # pre-scale board image
        if self.board_img:
            try:
                self.board_img_scaled = pygame.transform.smoothscale(self.board_img, (board_size, board_size))
            except Exception:
                self.board_img_scaled = pygame.transform.scale(self.board_img, (board_size, board_size))
        else:
            self.board_img_scaled = None

        # build board locations grid
        board_locations = []
        for x in range(8):
            row = []
            for y in range(8):
                px = bx + x * self.square_length
                py = by + y * self.square_length
                row.append([px, py])
            board_locations.append(row)

        pieces_src = os.path.join(self.resources, "pieces.png")
        if self.variant == "super" and HAS_SUPER:
            self.chess = SuperChess(self.screen, pieces_src, board_locations, self.square_length)
        else:
            self.chess = Chess(self.screen, pieces_src, board_locations, self.square_length)
        # ensure winner flag cleared when starting a new game/restart
        try:
            self.chess.winner = None
        except Exception:
            pass
        self.end_message = None


        # timers
        base = self.timer_presets.get(self.timer_mode, None)
    # Always set remaining to base value at start of new game/restart
        self.remaining = {"white": base, "black": base}  # Only set here, never elsewhere
        

        # HUD / visual bookkeeping
        self.hud = HUD(self, res_dir=RES_DIR)
        self.history = []
        self.snapshots = []
        self.preview_piece_location = None
        self.preview_highlight_move = None
        self._last_seen_move_id = None
        self.captured_white = []
        self.captured_black = []
         # DO NOT start turn_start_ticks here — timers begin after White's first move
        self.turn_start_ticks = None
        self.timers_started = False

    # ---------------- Playing loop/frame ----------------
    def loop_playing(self):
        """
        Main playing loop frame. Consolidated event handling and drawing.
        Replaces previous multiple-event-get patterns with a single unified pass.
        """
        resign_clicked = False

        # Precompute resign button rect so event handling can reference it (we don't draw it yet)
        resign_btn_w = 110
        resign_btn_w = 140
        resign_btn_w = 140
        resign_btn_h = 44
        resign_btn_x = self.right_panel_rect.x + 16
        resign_btn_y = self.right_panel_rect.y + 16
        # Store on self so other code can refer to it if needed
        self.resign_btn_rect = pygame.Rect(resign_btn_x, resign_btn_y, resign_btn_w, resign_btn_h)

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            # --- promotion overlay handling (highest priority) ---
            if getattr(self.chess, "promotion_pending", None) or getattr(self, "promotion_overlay", None):
                # initialize overlay if not already present
                if not getattr(self, "promotion_overlay", None):
                    self._init_promotion_overlay()

                # Mouse click -> finish promotion if clicked option
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx, my = ev.pos
                    handled = False
                    for r in self.promotion_overlay["rects"]:
                        if r["rect"].collidepoint(mx, my):
                            choice = r["opt"]
                            try:
                                pd = getattr(self.chess, "promotion_pending", None)
                                if pd:
                                    cf = pd["file"]; rr = pd["row"]; col = pd["color"]
                                    self.chess.piece_location[cf][rr][0] = f"{col}_{choice}"
                            except Exception:
                                try:
                                    self.chess.piece_location[cf][rr][0] = f"{col}_queen"
                                except Exception:
                                    pass
                            self._clear_promotion_overlay()
                            handled = True
                            break
                    if handled:
                        # swallow this event so it doesn't trigger other handlers
                        continue

                # Keyboard shortcuts to choose promotion
                if ev.type == pygame.KEYDOWN:
                    keymap = {pygame.K_1:0, pygame.K_2:1, pygame.K_3:2, pygame.K_4:3,
                            pygame.K_q:0, pygame.K_r:1, pygame.K_b:2, pygame.K_n:3}
                    idx = keymap.get(ev.key, None)
                    if idx is not None:
                        opts = self.promotion_overlay["options"] if self.promotion_overlay else ["queen","rook","bishop","knight"]
                        choice = opts[idx] if idx < len(opts) else opts[0]
                        try:
                            pd = getattr(self.chess, "promotion_pending", None)
                            if pd:
                                cf = pd["file"]; rr = pd["row"]; col = pd["color"]
                                self.chess.piece_location[cf][rr][0] = f"{col}_{choice}"
                        except Exception:
                            try:
                                self.chess.piece_location[cf][rr][0] = f"{col}_queen"
                            except Exception:
                                pass
                        self._clear_promotion_overlay()
                        continue

                # Debug quick-promote (press P to auto-queen) - optional, remove if undesired
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_p:
                    pd = getattr(self.chess, "promotion_pending", None)
                    if pd:
                        try:
                            cf = pd["file"]; rr = pd["row"]; col = pd["color"]
                            self.chess.piece_location[cf][rr][0] = f"{col}_queen"
                        except Exception:
                            pass
                        self._clear_promotion_overlay()
                        continue

                # while overlay is active, skip other handlers for this event/frame
                continue
            # --- end promotion overlay handling ---

            # HUD interception (visual-only)
            if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                try:
                    mx, my = ev.pos
                    if self.hud.rect(self.width, self.height).collidepoint(mx, my):
                        if self.hud.handle_event(ev):
                            continue
                except Exception:
                    pass

            # Keyboard shortcuts outside overlay
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if ev.key == pygame.K_SPACE:
                    self.start_variant()
                if ev.key == pygame.K_s:
                    # toggle preview if using SuperChess
                    if isinstance(self.chess, SuperChess):
                        if not self.chess.power_preview_active:
                            # lightning_sound should be defined in your environment; keep existing behavior
                            self.chess.start_power_preview_for_selected(lightning_sound)
                        else:
                            self.chess.cancel_power_preview()

            # Mouse button handling for board / preview / resign (left click)
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                mx, my = ev.pos

                # Resign button
                if self.resign_btn_rect.collidepoint(mx, my):
                    self.handle_resign()
                    return # Exit the function

                # SuperChess preview commit handling
                if isinstance(self.chess, SuperChess) and self.chess.power_preview_active:
                    clicked = False
                    for i in range(8):
                        for j in range(8):
                            r = pygame.Rect(self.board_top_left[0] + i*self.square_length,
                                            self.board_top_left[1] + j*self.square_length,
                                            self.square_length, self.square_length)
                            if r.collidepoint(mx, my):
                                if ([i, j] in self.chess.preview_moves) or ((i, j) in self.chess.preview_moves) or self.chess.preview_moves == [] or self.chess.power_preview_name in ("fortress_field","sacrifice"):
                                    self.chess.commit_power_preview((i,j))
                                    # Trigger superpower banner overlay
                                    self.superpower_banner = {
                                        'name': self.chess.power_preview_name,
                                        'start_time': time.time()
                                    }
                                else:
                                    self.chess.cancel_power_preview()
                                clicked = True
                                break
                        if clicked: break
                    continue

                # otherwise let chess engine pick up mouse state in move_piece()
                # (we intentionally do not call additional selection code here)

        # === end event processing ===

        # timers handling (per-frame)
        self.update_timers_and_timeout()

        # draw background
        self.screen.fill((28,28,28))

        # draw top HUD
        self.draw_top_hud()

        # --- Draw Resign Button ---
        # (recompute/draw so the button matches the rect used above)
        pygame.draw.rect(self.screen, (200, 24, 24), self.resign_btn_rect, border_radius=8)
        font = pygame.font.SysFont("comicsansms", 20)
        # Load resign icon if present
        try:
            resign_icon = None
            icon_path = os.path.join(self.resources, "resign.png")
            if os.path.exists(icon_path):
                resign_icon = pygame.image.load(icon_path).convert_alpha()
        except Exception:
            resign_icon = None
        label = font.render("Resign", True, (200, 200, 200))
        if resign_icon:
            icon_size = 24
            resign_icon = pygame.transform.smoothscale(resign_icon, (icon_size, icon_size))
            icon_x = self.resign_btn_rect.x + 10
            icon_y = self.resign_btn_rect.centery - icon_size // 2
            self.screen.blit(resign_icon, (icon_x, icon_y))
            text_x = icon_x + icon_size + 8
        else:
            text_x = self.resign_btn_rect.x + 10
        text_y = self.resign_btn_rect.centery - label.get_height() // 2
        self.screen.blit(label, (text_x, text_y))

        # draw captured side (under resign button)
        self.draw_captured_side(self.resign_btn_rect)

        # --- Auto-play preview if HUD play is active ---
        try:
            if getattr(self.hud, "replay_playing", False):
                now = pygame.time.get_ticks()
                last = getattr(self.hud, "replay_last_tick", None) or now
                interval = getattr(self.hud, "replay_interval_ms", 700)
                if now - last >= interval:
                    # step forward one index
                    try:
                        self.hud._on_replay_step(1)
                    except Exception:
                        traceback.print_exc()
                    # update last tick
                    self.hud.replay_last_tick = now

                    # if we've reached the final index, stop playback and return to live
                    history_len = len(getattr(self, "history", []) or [])
                    if history_len and (self.hud.replay_index is not None) and (self.hud.replay_index >= history_len - 1):
                        # finish playback: restore live state and stop
                        try:
                            self.hud._on_return_live()
                        except Exception:
                            traceback.print_exc()
                        self.hud.replay_playing = False
        except Exception:
            # non-fatal auto-play errors shouldn't crash the game loop
            traceback.print_exc()
            

        # draw board (squares + static board)
        if not getattr(self, "promotion_active", False):
            self.draw_board()   # whatever draws board & pieces in your loop
        else:
        # skip board redraw while promotion modal is active (the modal will draw itself)
            pass
        

        # draw promotion overlay (use atlas draw so icons show)
        if getattr(self, "promotion_overlay", None):
            data = self.promotion_overlay
            try:
                panel = pygame.Surface((data["width"], data["height"]), pygame.SRCALPHA)
                panel.fill((8, 80, 30, 220))
                font = pygame.font.SysFont(None, 18, bold=True)
                label = font.render("Promote to:", True, (240, 240, 240))
                panel.blit(label, ((data["width"] - label.get_width()) // 2, data.get("padding", 8)))
                self.screen.blit(panel, (data["ox"], data["oy"]))
            except Exception:
                pass

            # icons
            for r in data["rects"]:
                opt = r["opt"]; rect = r["rect"]
                drew = False
                try:
                    tmp = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
                    # IMPORTANT: use self.chess.chess_pieces (same renderer as board)
                    try:
                        self.chess.chess_pieces.draw(tmp, f"{data['color']}_{opt}", (0, 0))
                        icon = pygame.transform.smoothscale(tmp, (rect.w, rect.h))
                        self.screen.blit(icon, rect.topleft)
                        drew = True
                    except Exception:
                        drew = False
                except Exception:
                    drew = False

                if not drew:
                    pygame.draw.rect(self.screen, (60,60,60), rect, border_radius=4)
                    f2 = pygame.font.SysFont(None, 16)
                    short = "N" if opt == "knight" else opt[0].upper()
                    t = f2.render(short, True, (240,240,240))
                    self.screen.blit(t, (rect.x + (rect.w - t.get_width())//2, rect.y + (rect.h - t.get_height())//2))

            # hover highlight
            mx, my = pygame.mouse.get_pos()
            for r in data["rects"]:
                if r["rect"].collidepoint(mx, my):
                    try:
                        pygame.draw.rect(self.screen, (255,255,255), r["rect"], 2, border_radius=4)
                    except Exception:
                        pass

        # Draw fortress zones (red)
        if isinstance(self.chess, SuperChess) and getattr(self.chess, "fortress_zones", None):
            red_surf = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
            red_surf.fill((200, 24, 24, 120))
            for zone in self.chess.fortress_zones:
                for (zx, zy) in zone['squares']:
                    rx = self.board_top_left[0] + zx * self.square_length
                    ry = self.board_top_left[1] + zy * self.square_length
                    self.screen.blit(red_surf, (rx, ry))

        


        # draw pieces
        if not getattr(self, "promotion_active", False):
            self.chess.draw_pieces()  
        else:
        # skip board redraw while promotion modal is active (the modal will draw itself)
            pass
        

        # draw preview highlights if active
        if isinstance(self.chess, SuperChess) and self.chess.power_preview_active:
            yellow_surf = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
            yellow_surf.fill((255, 200, 20, 120))
            red_surf = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
            red_surf.fill((200, 24, 24, 140))

            pname = self.chess.power_preview_name
            if pname == "sacrifice" and self.chess.preview_source:
                sf, sr = self.chess.preview_source
                sx, sy = self.chess.piece_location[sf][sr][2]
                px = self.board_top_left[0] + sx * self.square_length
                py = self.board_top_left[1] + sy * self.square_length
                self.screen.blit(yellow_surf, (px, py))
                for ox in (-1, 1):
                    nx = sx + ox
                    ny = sy
                    if 0 <= nx < 8 and 0 <= ny < 8:
                        rx = self.board_top_left[0] + nx * self.square_length
                        ry = self.board_top_left[1] + ny * self.square_length
                        self.screen.blit(red_surf, (rx, ry))
            else:
                for mv in self.chess.preview_moves:
                    px, py = mv
                    rx = self.board_top_left[0] + px * self.square_length
                    ry = self.board_top_left[1] + py * self.square_length
                    self.screen.blit(yellow_surf, (rx, ry))

        # HUD (right panel, move history, replay controls)
        try:
            self.hud.draw(self.screen)
        except Exception:
            traceback.print_exc()

        # --- Auto-advance replay when Play is active ---
        try:
            if getattr(self, "hud", None) and getattr(self.hud, "replay_playing", False):
                now = pygame.time.get_ticks()
                interval = getattr(self.hud, "replay_interval_ms", 800)
                if now - getattr(self.hud, "replay_last_tick", 0) >= interval:
                    # advance one step
                    try:
                        self.hud._on_replay_step(1)
                    except Exception:
                        # fallback: directly ask controller to apply next index
                        try:
                            next_idx = (self.hud.replay_index or 0) + 1
                            self._apply_replay_index_to_preview(next_idx)
                            self.hud.replay_index = next_idx
                            self.hud.selected_idx = next_idx
                        except Exception:
                            pass
                    # update last tick
                    try:
                        self.hud.replay_last_tick = now
                    except Exception:
                        pass

                    # if we reached the final history index, return to live and stop playing
                    try:
                        if self.hud.replay_index is not None and self.hud.replay_index >= len(getattr(self, "history", [])) - 1:
                            self.hud._on_return_live()
                    except Exception:
                        pass
        except Exception:
            # don't let replay errors crash the main loop
            pass

        # winner handling
        if getattr(self, "state", "") == "playing":
            w = getattr(self.chess, "winner", None)
            if w not in (None, False, ""):
                if w == "Stalemate":
                    self.end_message = "Tie by Stalemate!"
                elif w == "Threefold":
                    self.end_message = "Draw by Threefold Repetition!"
                elif w == "InsufficientMaterial":
                    self.end_message = "Draw by insufficient material!"
                elif w == "Timeout":
                    if not getattr(self, "end_message", None):
                        loser = getattr(self, "current_turn_color", None)
                        if loser in ("white", "black"):
                            winner_side = "white" if loser == "black" else "black"
                            winner_name = self.name_white if winner_side == "white" else self.name_black
                            self.end_message = f"{winner_name} wins on time!"
                        else:
                            self.end_message = "Win by timeout!"
                else:
                    try:
                        if str(w).lower() in ("white", "black"):
                            winner_name = self.name_white if str(w).lower() == "white" else self.name_black
                            self.end_message = f"{winner_name} wins!"
                        else:
                            self.end_message = f"{w} wins!"
                    except Exception:
                        self.end_message = f"{w} wins!"
                self.state = "end"
        
        # --- Superpower Banner Overlay (modal, always on top) ---
        if hasattr(self, 'superpower_banner') and self.superpower_banner:
            elapsed = time.time() - self.superpower_banner['start_time']
            duration = 2.0
            fade_duration = 0.5
            banner_map = {
                "sacrifice": "sacrifice.png",
                "thunder": "thunder.png",
                "shadow_jump": "shadow_jump.png",
                "royal_teleport": "royal_teleport.png",
                "fortress_field": "fortress_zone.png",
                "dark_empress": "dark_empress.png",
                "phase_shift": "phase_shift.png"  
            }
            fname = banner_map.get(self.superpower_banner['name'])
            if fname:
                img_path = os.path.join(self.resources, fname)
                if os.path.exists(img_path):
                    try:
                        banner_img = pygame.image.load(img_path).convert_alpha()
                        w, h = self.board_rect.width, self.board_rect.height
                        banner_img = pygame.transform.smoothscale(banner_img, (w, h))
                        # Fade out effect
                        if elapsed < duration:
                            alpha = 255
                        elif elapsed < duration + fade_duration:
                            alpha = int(255 * (1 - (elapsed - duration) / fade_duration))
                        else:
                            alpha = 0
                        print(f"[DEBUG] Banner: {self.superpower_banner}")
                        if alpha > 0:
                            faded = banner_img.copy()
                            faded.fill((255,255,255,alpha), special_flags=pygame.BLEND_RGBA_MULT)
                            self.screen.blit(faded, (self.board_rect.x, self.board_rect.y))
                        else:
                            self.superpower_banner = None
                    except Exception as e:
                        pass
                else:
                    self.superpower_banner = None
            else:
                self.superpower_banner = None

        # let chess handle input & moves (it reads mouse events via Utils)
        side = "black" if self.chess.turn["black"] else "white"
        self.chess.move_piece(side)

        # If vs AI and black to move then call ai_move()
        if self.game_mode == "engine" and (not self.chess.winner) and (not self.chess.turn["white"]):
            pygame.time.delay(180)
            self.chess.ai_move()

        self.record_last_move()

        # check insufficient-material draw (only kings)
        try:
            if self.state == "playing" and self._only_kings_left():
                try:
                    self.chess.winner = "InsufficientMaterial"
                except Exception:
                    pass
                self.end_message = "Draw by insufficient material!"
                self.state = "end"
                pygame.display.flip()
                self.clock.tick(60)
                return
        except Exception:
            pass

        # detect turn change and adjust timers
        new_turn = "black" if self.chess.turn["black"] else "white"
        if new_turn != self.current_turn_color:
            # commit elapsed to the player who just moved
            self.commit_elapsed_to_remaining(self.current_turn_color)

            moved_side = self.current_turn_color
            self.current_turn_color = new_turn

            # only start timers once White has moved
            if not self.timers_started:
                if moved_side == "white":
                    self.timers_started = True
                    self.turn_start_ticks = pygame.time.get_ticks()
                else:
                    self.turn_start_ticks = None
            else:
                # only reset the tick reference when switching to the new player
                self.turn_start_ticks = pygame.time.get_ticks()

        # --- Soft yellow underlay for history preview only ---
            try:
                if getattr(self.hud, "preview_active", False):
                    ph = getattr(self, "preview_highlight_move", None)
                    if ph:
                        yellow_surf = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
                        yellow_surf.fill((255, 230, 140, 140))  # soft semi-transparent yellow
                        try:
                            src, dst = ph
                            for sq in (src, dst):
                                sx, sy = sq
                                rx = self.board_top_left[0] + sx * self.square_length
                                ry = self.board_top_left[1] + sy * self.square_length
                                # Cover the whole square with a soft yellow overlay
                                s = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
                                s.fill(PREVIEW_YELLOW)
                                self.screen.blit(s, (rx, ry))
                        except Exception:
                            # don't let drawing errors crash the loop
                            traceback.print_exc()
            except Exception:
                pass

        pygame.display.flip()
        self.clock.tick(60)

    # ---------------- timers ----------------
    def commit_elapsed_to_remaining(self, color):
        """
        Safely subtract elapsed time since turn_start_ticks from remaining[color].

        Defensive behavior:
        - If remaining[color] is None or missing -> do nothing (no TypeError).
        - Only runs when timers_started is True and turn_start_ticks is valid.
        - Converts values to float, clamps at 0.0, and advances turn_start_ticks
        so repeated commits don't double-subtract.
        """
        try:
            # basic guards
            if color is None:
                return
            if not getattr(self, "timers_started", False):
                return
            ts = getattr(self, "turn_start_ticks", None)
            if not ts:
                return

            # safely obtain remaining for color
            try:
                rem = None
                if isinstance(self.remaining, dict):
                    rem = self.remaining.get(color, None)
                else:
                    # fallback: try attribute access or indexing
                    try:
                        rem = getattr(self.remaining, color)
                    except Exception:
                        try:
                            rem = self.remaining[color]
                        except Exception:
                            rem = None
            except Exception:
                rem = None

            # if there's no numeric remaining value, bail out safely
            if rem is None:
                return

            # compute elapsed
            now = pygame.time.get_ticks()
            elapsed = (now - ts) / 1000.0
            if elapsed <= 0:
                return

            # subtract and clamp, defensively converting to float
            try:
                new_val = float(rem) - float(elapsed)
            except Exception:
                return
            self.remaining[color] = max(0.0, new_val)

            # advance baseline so subsequent commits are incremental
            self.turn_start_ticks = now

        except Exception:
            # never raise from UI timer helper; print for debugging
            import traceback
            traceback.print_exc()
            return


    def update_timers_and_timeout(self):
        """
        Called each frame to check the running player's clock and end the game on timeout.
        This version sets the UI end_message and transitions state to 'end' immediately so
        later winner-handling won't overwrite the timeout message.
        """
        # timers must have been started by White's first move
        if not getattr(self, "timers_started", False):
            return

        color = self.current_turn_color
        if self.remaining.get(color) is None:
            return
        if not self.turn_start_ticks:
            return

        now = pygame.time.get_ticks()
        elapsed = (now - self.turn_start_ticks) / 1000.0
        left = self.remaining[color] - elapsed

        if left <= 0:
            # The side 'color' ran out of time -> the other side wins on time.
            loser = color
            winner_side = "white" if loser == "black" else "black"
            winner_name = self.name_white if winner_side == "white" else self.name_black

            # Set a definitive UI message and end the game immediately.
            # Doing this here prevents the generic winner-handling later from overwriting it.
            self.end_message = f"{winner_name} wins on time!"
            try:
                # indicate timeout at engine level too (optional)
                self.chess.winner = "Timeout"
            except Exception:
                pass

            # move to end state now
            self.state = "end"

            # return early — we've ended the game due to timeout
            return



                
    def draw_glass_panel(self, rect, color=(255,255,255), alpha=110, border=True, border_radius=12):
        """
        rect: pygame.Rect
        Draws a semi-transparent 'glass' panel at rect.
        alpha: 0..255 (0 transparent, 255 fully opaque)
        """
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((color[0], color[1], color[2], alpha))
        if border:
            # subtle border
            pygame.draw.rect(surf, (255,255,255,30), surf.get_rect(), width=1, border_radius=border_radius)
        self.screen.blit(surf, (rect.x, rect.y))



    # ---------------- drawing helpers ----------------
    def draw_board(self):
        yellow = (255, 230, 80, 200)  # more visible yellow
        # board background
        if self.board_img_scaled:
            self.screen.blit(self.board_img_scaled, self.board_top_left)
        else:
            light = (246,246,238); dark = (120,120,90)
            for x in range(8):
                for y in range(8):
                    r = pygame.Rect(self.board_top_left[0] + x*self.square_length,
                                    self.board_top_left[1] + y*self.square_length,
                                    self.square_length, self.square_length)
                    pygame.draw.rect(self.screen, light if (x+y)%2==0 else dark, r)

        # file labels a..h bottom, rank labels left
        fnt = pygame.font.SysFont("consolas", max(14, self.square_length//4))
        files = "abcdefgh"
        for i,ch in enumerate(files):
            tx = fnt.render(ch, True, (200,200,200))
            x = self.board_top_left[0] + i*self.square_length + self.square_length//2 - tx.get_width()//2
            y = self.board_top_left[1] + 8*self.square_length + 6
            self.screen.blit(tx,(x,y))
        for j in range(8):
            num = 8 - j
            tx = fnt.render(str(num), True, (200,200,200))
            x = self.board_top_left[0] - 18
            y = self.board_top_left[1] + j*self.square_length + self.square_length//2 - tx.get_height()//2
            self.screen.blit(tx,(x,y))

        # --- Soft yellow underlay for history preview only ---
        highlight_drawn = False
        try:
            if getattr(self.hud, "preview_active", False):
                ph = getattr(self, "preview_highlight_move", None)
                preview_idx = getattr(self.hud, "preview_index", 0)
            
                if ph:
                    src, dst = ph
                    def valid_sq(sq):
                        if not isinstance(sq, (tuple, list)) or len(sq) != 2:
                            return False
                        sx, sy = sq
                        return 0 <= sx < 8 and 0 <= sy < 8
                    # Try to get piece type from preview move meta
                    piece_type = None
                    try:
                        idx = getattr(self.hud, "preview_index", 0)
                        if idx >= 0 and hasattr(self, 'history') and len(self.history) > idx:
                            move_entry = self.history[idx]
                            meta = move_entry.get('meta')
                            if meta:
                                piece_type = meta.get('piece', None)
                    except Exception:
                        piece_type = None
                    squares_to_highlight = []
                    if valid_sq(src) and valid_sq(dst):
                        squares_to_highlight.append(src)
                        squares_to_highlight.append(dst)
                        # Highlight path for sliding pieces
                        if piece_type:
                            pt = piece_type.lower()
                            if any(x in pt for x in ["bishop", "rook", "queen"]):
                                sx, sy = src
                                dx, dy = dst
                                x_step = (dx - sx)
                                y_step = (dy - sy)
                                if x_step != 0:
                                    x_step = int(x_step / abs(x_step))
                                if y_step != 0:
                                    y_step = int(y_step / abs(y_step))
                                x, y = sx + x_step, sy + y_step
                                while (x, y) != (dx, dy):
                                    if valid_sq((x, y)):
                                        squares_to_highlight.append((x, y))
                                    x += x_step
                                    y += y_step
                    for sq in squares_to_highlight:
                        sx, sy = sq
                        rx = self.board_top_left[0] + sx * self.square_length
                        ry = self.board_top_left[1] + sy * self.square_length
                        s = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
                        s.fill(yellow)
                        self.screen.blit(s, (rx, ry))
                    highlight_drawn = True
        except Exception as e:
            print(f"[DEBUG] Highlight error: {e}")
        # ...existing code...
    def draw_top_hud(self):
        # top bar background
        bar_h = self.TOP_BAR - 8
        pygame.draw.rect(self.screen, (16,16,16), (0,0,self.width, bar_h))
        # center turn indicator
        big = pygame.font.SysFont("comicsansms", 26)
        turn_text = f"Turn: {'Black' if self.current_turn_color == 'black' else 'White'}"
        txt = big.render(turn_text, True, (220,220,220))
        self.screen.blit(txt, (self.width//2 - txt.get_width()//2, 8))

        # (no names or timers shown here — moved to right HUD)


    
            
    def draw_captured_side(self, anchor_rect):
        """Draw a captured-pieces card inside the right panel, anchored under `anchor_rect` (Resign button)."""
        try:
            captured = getattr(self.chess, "captured", []) or []
            # normalize to strings
            flat = []
            for it in captured:
                if isinstance(it, str):
                    flat.append(it)
                elif isinstance(it, (list,tuple)) and it:
                    flat.append(it[0] if isinstance(it[0], str) else str(it))
                else:
                    flat.append(str(it))

            white_lost = [p for p in flat if p.startswith("white_")]
            black_lost = [p for p in flat if p.startswith("black_")]

            # layout inside right panel below anchor_rect
            fixed_card_w = 220
            cap_w = fixed_card_w
            cap_x = self.right_panel_rect.x + 12
            cap_y = anchor_rect.bottom + 12
            icon_size = min(48, max(18, self.square_length // 3))
            max_per_row = 8  # Fixed value for better wrapping
            # Calculate rows needed for each color
            white_rows = (len(white_lost) + max_per_row - 1) // max_per_row
            black_rows = (len(black_lost) + max_per_row - 1) // max_per_row
            total_rows = white_rows + black_rows
            row_height = icon_size + 8
            cap_h = 36 + total_rows * row_height + 8

            # background card (draw after calculating cap_h)
            pygame.draw.rect(self.screen, (34,34,34), (cap_x, cap_y, cap_w, cap_h), border_radius=8)
            # header
            hdr_font = pygame.font.SysFont(None, 16)
            hdr = hdr_font.render("Captured Pieces", True, (200,200,200))
            self.screen.blit(hdr, (cap_x + 8, cap_y + 8))

            start_x = cap_x + 8
            def _draw_rows(pieces, start_y):
                y = start_y
                for i in range(0, len(pieces), max_per_row):
                    row_pieces = pieces[i:i+max_per_row]
                    x = start_x
                    for p in row_pieces:
                        # Clamp icon so it never overflows right border
                        if x + icon_size > cap_x + cap_w:
                            break
                        try:
                            surf = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
                            self.chess.chess_pieces.draw(surf, p, (0, 0))
                            icon = pygame.transform.smoothscale(surf, (icon_size, icon_size))
                            self.screen.blit(icon, (x, y))
                        except Exception:
                            pygame.draw.rect(self.screen, (120,120,120), (x, y, icon_size, icon_size), border_radius=6)
                        x += icon_size + 6
                    y += row_height
                return y

            next_y = cap_y + 36
            next_y = _draw_rows(white_lost, next_y)
            _draw_rows(black_lost, next_y)
        except Exception:
            # visual-only; do not raise or change game logic
            pass


    
    def snapshot_game_state(self):
        """
        Create a deep snapshot of the engine state used for history/preview.
        We include common castling/move flags so restores don't lose castling rights.
        """
        snap = {}
        # deep-copy main board/piece map (adjust key if your engine uses different name)
        try:
            snap['piece_location'] = copy.deepcopy(getattr(self.chess, 'piece_location', {}))
        except Exception:
            snap['piece_location'] = {}

        # include move history, turn, FEN-like fields if present
        for attr in ('turn', 'move_history', 'halfmove_clock', 'fullmove_number'):
            if hasattr(self.chess, attr):
                try:
                    snap[attr] = copy.deepcopy(getattr(self.chess, attr))
                except Exception:
                    snap[attr] = getattr(self.chess, attr)

        # Defensive: capture common castling/move flags so restores preserve castling rights
        castling_attrs = [
            'castling_rights', 'castle_rights', 'can_castle', 'can_castle_kingside',
            'can_castle_queenside', 'can_castle_white', 'can_castle_black',
            'has_moved', 'king_moved', 'rook_moved', 'castles',
            'white_can_castle_kingside','white_can_castle_queenside',
            'black_can_castle_kingside','black_can_castle_queenside'
        ]
        for a in castling_attrs:
            if hasattr(self.chess, a):
                try:
                    snap[a] = copy.deepcopy(getattr(self.chess, a))
                except Exception:
                    snap[a] = getattr(self.chess, a)

        # include captured pieces and last-move metadata so previews can highlight correctly
        try:
            snap['captured'] = copy.deepcopy(getattr(self.chess, 'captured', []) or [])
        except Exception:
            snap['captured'] = []
        try:
            snap['last_move_meta'] = copy.deepcopy(getattr(self.chess, 'last_move_meta', None))
        except Exception:
            snap['last_move_meta'] = None
        try:
            snap['last_move'] = copy.deepcopy(getattr(self.chess, 'last_move', None))
        except Exception:
            snap['last_move'] = None

        # other metadata useful for UI preview
        snap['_timestamp'] = time.time()
        return snap


    def restore_game_state(self, snap):
        """
        Restore a snapshot previously created by snapshot_game_state.
        Only restores visual/engine state fields and castling flags; does not alter UI stacks.
        """
        if not snap:
            return

        # restore main piece map if present
        try:
            if 'piece_location' in snap:
                # replace engine's piece_location with the snapshot's copy
                setattr(self.chess, 'piece_location', copy.deepcopy(snap['piece_location']))
        except Exception:
            pass

        # restore simple attributes if present
        for attr in ('turn', 'move_history', 'halfmove_clock', 'fullmove_number'):
            if attr in snap:
                try:
                    setattr(self.chess, attr, copy.deepcopy(snap[attr]))
                except Exception:
                    try:
                        setattr(self.chess, attr, snap[attr])
                    except Exception:
                        pass

        # restore castling/move flags
        castling_attrs = [
            'castling_rights', 'castle_rights', 'can_castle', 'can_castle_kingside',
            'can_castle_queenside', 'can_castle_white', 'can_castle_black',
            'has_moved', 'king_moved', 'rook_moved', 'castles',
            'white_can_castle_kingside','white_can_castle_queenside',
            'black_can_castle_kingside','black_can_castle_queenside'
        ]
        for a in castling_attrs:
            if a in snap:
                try:
                    setattr(self.chess, a, copy.deepcopy(snap[a]))
                except Exception:
                    try:
                        setattr(self.chess, a, snap[a])
                    except Exception:
                        pass

        # optional: if engine uses a fen string representation, restore if present
        if 'fen' in snap and hasattr(self.chess, 'set_fen'):
            try:
                self.chess.set_fen(snap['fen'])
            except Exception:
                pass

        # After restoring, request a board redraw in the UI (non-invasive)
        try:
            self.update_board_visuals()
        except Exception:
            # some codebases use a different redraw method; ignore if not available
            pass


    

    def _apply_replay_index_to_preview(self, idx):
        """
        Apply a history index for preview/stepping.
        - Applies the snapshot (via replay_to_index) so the engine/board reflect that history index.
        - Plays a move or capture sound when stepping through history so audio matches the visual preview.
        Returns True on success, False otherwise.
        """
        try:
            if idx is None:
                return False

            # let replay_to_index handle most of the snapshot/apply UI state (it sets hud.preview_snapshot, preview flags, etc.)
            ok = False
            try:
                ok = self.replay_to_index(idx)
            except Exception:
                # fallback: if replay_to_index isn't available for some reason try original preview application below
                ok = False

            # If replay_to_index applied the snapshot, play the appropriate sound for that index.
            # Determine if the step involved a capture by comparing `captured` lengths between snapshots.
            try:
                snap_idx = idx + 1 if idx + 1 < len(self.snapshots) else idx
                if 0 <= snap_idx < len(self.snapshots):
                    snap = self.snapshots[snap_idx]
                    eng = snap.get('engine', snap)
                    # find previous snapshot's captured count (if exists)
                    prev_captured_len = 0
                    prev_idx = snap_idx - 1
                    if prev_idx >= 0 and prev_idx < len(self.snapshots):
                        prev_snap = self.snapshots[prev_idx]
                        prev_eng = prev_snap.get('engine', prev_snap)
                        prev_captured_len = len(prev_eng.get('captured', []) or [])

                    cur_captured_len = len(eng.get('captured', []) or [])
                    captures = cur_captured_len > prev_captured_len

                    # Play capture/move sound so stepping has audio feedback.
                    # Use module-level move_sound / capture_sound if they exist.
                    try:
                        if captures:
                            try:
                                capture_sound.play()
                            except Exception:
                                pass
                        else:
                            try:
                                move_sound.play()
                            except Exception:
                                pass
                    except Exception:
                        # ignore if sounds unavailable; preview should remain functional
                        pass

                    # If replay_to_index didn't run above, also set minimal preview state for backward compatibility
                    if not ok:
                        pl = eng.get('piece_location')
                        self.preview_piece_location = safe_deepcopy(pl)
                        lm = eng.get('last_move_meta') or eng.get('last_move')
                        self.preview_highlight_move = None
                        if lm:
                            try:
                                if isinstance(lm, dict):
                                    src = lm.get('src'); dst = lm.get('dst')
                                else:
                                    src, dst = lm[0], lm[1]
                                if src is not None and dst is not None:
                                    # unify to internal highlight tuple format used elsewhere
                                    self.preview_highlight_move = ((int(src[0]), int(src[1])), (int(dst[0]), int(dst[1])))
                            except Exception:
                                self.preview_highlight_move = None

                        self.hud.preview_active = True
                        self.hud.replay_mode = True
                        self.hud.replay_index = idx
                        self.hud.selected_idx = idx
                        # if last index, automatically return to live UI (keeps behaviour consistent)
                        if idx == len(self.history) - 1:
                            try:
                                self.hud._on_return_live()
                            except Exception:
                                pass

                    return True

            except Exception:
                # swallow sound/preview errors so stepping doesn't crash the app
                traceback.print_exc()
                return ok if ok else False

            return ok
        except Exception:
            traceback.print_exc()
            return False


    def start_replay_preview(self, idx, destructive=False):
        return self.replay_to_index(idx, destructive=destructive)

    def replay_to_index(self, idx,destructive=False):
        """
        Jump to history index `idx` for preview. This now restores the engine snapshot so
        board and castling flags are accurate for the preview.
        """
        if not (0 <= idx < len(self.snapshots)):
            return

        snap = self.snapshots[idx]

        # restore engine state for preview (visual-only, we keep a saved live copy elsewhere)
        try:
            # keep a copy of the current live state if not already saved
            if not hasattr(self, 'live_snapshot'):
                self.live_snapshot = self.snapshot_game_state()
        except Exception:
            pass

        # apply the chosen historical snapshot to the engine so preview shows the correct position
        try:
            self.restore_game_state(snap)
        except Exception:
            pass

        # set preview UI markers so other parts of the UI know we're previewing
        self.previewing = True
        self.preview_index = idx
        # let the HUD know (if you have such a field)
        try:
            self.hud.preview_snapshot = snap
            self.hud.preview_index = idx
        except Exception:
            pass
                # set preview piece map and highlight move based on restored engine state
        try:
            self.preview_piece_location = safe_deepcopy(getattr(self.chess, 'piece_location', None))

            self.preview_highlight_move = None
            # Use move history for highlight if available
            if idx >= 0 and hasattr(self, 'history') and len(self.history) > idx:
                move_entry = self.history[idx]
               
                meta = move_entry.get('meta')
                def file_to_idx(f):
                    if isinstance(f, str):
                        return ord(f.lower()) - ord('a')
                    return int(f)
                def rank_to_idx(r):
                    return 7 - (int(r) - 1) if isinstance(r, int) and 1 <= r <= 8 else 7 - (int(r) - 1)
                src = dst = None
                if meta:
                    src = meta.get('src') or meta.get('from') or meta.get('from_sq')
                    dst = meta.get('dst') or meta.get('to') or meta.get('to_sq')
                    # If src is missing but dst is present, try to infer src for pawn pushes
                    if dst and not src and meta.get('piece', '').endswith('pawn'):
                        dst_file = dst[0] if isinstance(dst[0], str) else chr(ord('a') + dst[0])
                        dst_rank = int(dst[1]) if not isinstance(dst[1], int) else dst[1]
                        color = meta.get('color', None)
                        if color == 'white' and dst_file in 'abcdefgh':
                            # White pawn single push: from rank 2 to 3, double push: from 2 to 4
                            if dst_rank == 3:
                                src = (dst_file, '2')
                            elif dst_rank == 4:
                                src = (dst_file, '2')
                            elif dst_rank > 4 and dst_rank <= 8:
                                # fallback: infer previous rank
                                src = (dst_file, str(dst_rank - 1))
                        elif color == 'black' and dst_file in 'abcdefgh':
                            # Black pawn single push: from rank 7 to 6, double push: from 7 to 5
                            if dst_rank == 6:
                                src = (dst_file, '7')
                            elif dst_rank == 5:
                                src = (dst_file, '7')
                            elif dst_rank < 5 and dst_rank >= 1:
                                # fallback: infer previous rank
                                src = (dst_file, str(dst_rank + 1))
                    if src is not None and dst is not None:
                        try:
                            def to_index(sq):
                                # If file is str and rank is 1-8, convert
                                if isinstance(sq, (tuple, list)) and len(sq) == 2:
                                    file, rank = sq
                                    # file/rank notation
                                    if isinstance(file, str):
                                        fx = file_to_idx(file)
                                        fr = int(rank) if not isinstance(rank, int) else rank
                                        fy = rank_to_idx(fr)
                                        return (fx, fy)
                                    # already indices
                                    elif isinstance(file, int) and isinstance(rank, int):
                                        return (file, rank)
                                return None
                            src_idx = to_index(src)
                            dst_idx = to_index(dst)
                            # Only highlight if src and dst are distinct and valid
                            if src_idx and dst_idx and (0 <= src_idx[0] < 8 and 0 <= src_idx[1] < 8 and 0 <= dst_idx[0] < 8 and 0 <= dst_idx[1] < 8 and src_idx != dst_idx):
                                self.preview_highlight_move = (src_idx, dst_idx)
                            else:
                                self.preview_highlight_move = None
                        except Exception:
                            self.preview_highlight_move = None
                else:
                    # fallback for engines that use last = (src, dst, piece)
                    last = move_entry.get('last')
                    if last and isinstance(last, (list, tuple)) and len(last) >= 2:
                        src, dst = last[0], last[1]
                        if src is not None and dst is not None:
                            self.preview_highlight_move = ((int(src[0]), int(src[1])), (int(dst[0]), int(dst[1])))

            # let HUD know we're previewing this index
            try:
                self.hud.preview_active = True
                self.hud.replay_mode = True
                self.hud.replay_index = idx
                self.hud.selected_idx = idx
            except Exception:
                pass
        except Exception:
            pass

        # force a redraw to show the restored snapshot immediately
        try:
            self.draw_board()
            pygame.display.flip()
        except Exception:
            pass

        # indicate success to callers
        return True




    def record_last_move(self):
        """
        Inspect chess.last_move / last_move_meta and append to history only once.
        IMPORTANT: this function intentionally does NOT manipulate timer timestamps.
        The main loop's turn-change logic (loop_playing) is the single place that
        should change self.turn_start_ticks / self.timers_started.
        """
        try:
            # don't record moves while previewing or after game end
            if getattr(self.hud, "preview_active", False) or getattr(self.hud, "replay_mode", False) or self.state == "end":
                return

            e = self.chess
            meta = getattr(e, "last_move_meta", None)
            if meta is not None:
                fingerprint = str(meta)
                if fingerprint == getattr(self, "_last_seen_move_id", None):
                    return

                san = self._meta_to_san(meta)
                power = meta.get('type') if meta.get('type') and meta.get('type') != 'move' else None

                # play move/capture sound
                captured = meta.get('captured', [])
                try:
                    if captured:
                        capture_sound.play()
                    else:
                        move_sound.play()
                except Exception:
                    pass

                entry = {'idx': len(self.history), 'san': san, 'meta': safe_deepcopy(meta), 'power': power}
                self.history.append(entry)
                snap = self.snapshot_game_state()
                self.snapshots.append(snap)

                # set seen id and HUD index
                self._last_seen_move_id = fingerprint
                self.hud.selected_idx = len(self.history) - 1

                # start timers when the first move is recorded (useful for vs AI and consistent behavior)
                try:
                    if not getattr(self, "timers_started", False):
                        # only start if timers are enabled (non-timeless)
                        if (self.remaining.get("white") is not None) or (self.remaining.get("black") is not None):
                            self.timers_started = True
                            # begin counting for the side to move now (the opponent of the player who just moved)
                            self.turn_start_ticks = pygame.time.get_ticks()
                except Exception:
                    pass


                # If after this move only kings remain -> draw by insufficient material
                try:
                    if self._only_kings_left():
                        # set engine/UI end state
                        try:
                            self.chess.winner = "InsufficientMaterial"
                        except Exception:
                            pass
                        self.end_message = "Draw by insufficient material!"
                        self.state = "end"
                        return
                except Exception:
                    pass

                # sync captured visuals (visual-only)
                try:
                    self._sync_captured_display()
                except Exception:
                    pass

                return

            # fallback for engines that use last = (src, dst, piece)
            last = getattr(e, "last_move", None)
            if last is None:
                return
            fp_last = str(last)
            if fp_last == getattr(self, "_last_seen_move_id", None):
                return

            try:
                src, dst, piece = last[0], last[1], last[2]
            except Exception:
                src = dst = piece = None

            captures = False
            try:
                captures = len(getattr(e, "captured", [])) > (len(self.captured_white) + len(self.captured_black))
            except Exception:
                captures = False

            # play corresponding sound
            try:
                if captures:
                    capture_sound.play()
                else:
                    move_sound.play()
            except Exception:
                pass

            san = self._build_san_fallback(piece, src, dst, captures)
            entry = {'idx': len(self.history), 'san': san, 'meta': None, 'power': None}
            self.history.append(entry)
            snap = self.snapshot_game_state()
            self.snapshots.append(snap)

            # insufficient material detection
            try:
                if self._only_kings_left():
                    try:
                        self.chess.winner = "InsufficientMaterial"
                    except Exception:
                        pass
                    self.end_message = "Draw by insufficient material!"
                    self.state = "end"
                    return
            except Exception:
                pass

            self._last_seen_move_id = fp_last
            self.hud.selected_idx = len(self.history) - 1

            try:
                self._sync_captured_display()
            except Exception:
                pass

        except Exception:
            traceback.print_exc()



    def _meta_to_san(self, meta):
        try:
            piece = meta.get('piece', '')
            dst = meta.get('dst')
            captured = meta.get('captured', [])
            if dst is None:
                return f"{piece}*"
            dx, dy = int(dst[0]), int(dst[1])
            df, dr = self.chess.xy_to_square(dx, dy)
            dest = f"{df}{dr}"
            piece_kind = piece.split("_",1)[1] if "_" in piece else piece
            LETTER = {"king":"K","queen":"Q","rook":"R","bishop":"B","knight":"N","pawn":""}
            letter = LETTER.get(piece_kind.lower(), "")
            capture_flag = 'x' if captured else ''
            if piece_kind.lower() == "pawn":
                src = meta.get('src')
                if src:
                    src_file = src[0]
                    if capture_flag:
                        return f"{src_file}x{dest}"
                    return f"{dest}"
                return f"{dest}"
            return f"{letter}{capture_flag}{dest}"
        except Exception:
            return str(meta)

    def _build_san_fallback(self, piece, src_xy, dst_xy, capture):
        try:
            if not dst_xy:
                return str(piece)
            dx, dy = int(dst_xy[0]), int(dst_xy[1])
            df, dr = self.chess.xy_to_square(dx, dy)
            dest = f"{df}{dr}"
            piece_kind = piece.split("_",1)[1] if "_" in piece else piece
            letter = {"king":"K","queen":"Q","rook":"R","bishop":"B","knight":"N","pawn":""}.get(piece_kind.lower(), "")
            if piece_kind.lower() == "pawn":
                if src_xy:
                    sf, sr = self.chess.xy_to_square(int(src_xy[0]), int(src_xy[1]))
                    if capture:
                        return f"{sf}x{dest}"
                if capture:
                    return f"x{dest}"
                return f"{dest}"
            return f"{letter}{'x' if capture else ''}{dest}"
        except Exception:
            return f"{piece}->{dst_xy}"

    def _sync_captured_display(self):
        try:
            cap = getattr(self.chess, "captured", []) or []
            wlst = []; blst = []
            # Only add to captured if the last move actually captured something
            meta = getattr(self.chess, "last_move_meta", None)
            valid_captures = meta.get('captured', []) if meta and isinstance(meta, dict) else []
            if valid_captures:
                for it in cap:
                    lab = None
                    if isinstance(it, str):
                        lab = it
                    elif isinstance(it, (list,tuple)) and it:
                        lab = it[0]
                    else:
                        lab = str(it)
                    if not lab:
                        continue
                    lname = lab.lower()
                    if lname.startswith("white_") or "white" in lname:
                        wlst.append(lab)
                    else:
                        blst.append(lab)
            self.captured_white = wlst
            self.captured_black = blst
        except Exception:
            self.captured_white = []
            self.captured_black = []

    # ---------------- end screen ----------------
    def end_screen(self):
        big = pygame.font.SysFont("comicsansms", 46)
        small = pygame.font.SysFont("comicsansms", 24)
        msg = getattr(self, "end_message", "Game Over")
        btn_menu = pygame.Rect(self.width//2 - 180, self.height//2 + 100, 160, 64)
        btn_restart = pygame.Rect(self.width//2 + 20, self.height//2 + 100, 160, 64)
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if ev.type == KEYDOWN and ev.key == K_ESCAPE:
                    pygame.quit(); sys.exit()
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if btn_menu.collidepoint(ev.pos):
                        self.state = "menu"
                        self.chess = None
                        return
                    if btn_restart.collidepoint(ev.pos):
                        self.start_variant()
                        self.state = "playing"
                        return
            self.screen.fill((245,245,245))
            t = big.render(msg, True, (10,10,10))
            self.screen.blit(t, (self.width//2 - t.get_width()//2, self.height//2 - 90))
            pygame.draw.rect(self.screen, (10,10,10), btn_menu, border_radius=8)
            pygame.draw.rect(self.screen, (10,10,10), btn_restart, border_radius=8)
            lab_menu = small.render("Main Menu", True, (255,255,255))
            lab_restart = small.render("Restart", True, (255,255,255))
            self.screen.blit(lab_menu, (btn_menu.centerx - lab_menu.get_width()//2, btn_menu.centery - lab_menu.get_height()//2))
            self.screen.blit(lab_restart, (btn_restart.centerx - lab_restart.get_width()//2, btn_restart.centery - lab_restart.get_height()//2))
            pygame.display.flip()
            self.clock.tick(60)

    def handle_resign(self):
        # The current player resigns, so the other player wins
        loser = self.current_turn_color
        winner = "white" if loser == "black" else "black"
        winner_name = self.name_white if winner == "white" else self.name_black
        self.end_message = f"{winner_name} wins by resignation!"
        self.chess.winner = winner_name
        self.state = "end"

        #condition to check if only kings left

    def _only_kings_left(self):
        """
        Return True if there are NO pieces on the board other than kings.
        This tries several engine data layouts (dict of piece_location, lists, or piece objects)
        so it works across engine variants.
        """
        try:
            pieces = []
            pl = getattr(self.chess, "piece_location", None)
            if isinstance(pl, dict):
                for v in pl.values():
                    if v is None:
                        continue
                    # flatten lists/tuples
                    if isinstance(v, (list, tuple)):
                        for item in v:
                            if item is not None:
                                pieces.append(item)
                    else:
                        pieces.append(v)
            else:
                # fallback to common fields
                allp = getattr(self.chess, "pieces", None) or getattr(self.chess, "all_pieces", None)
                if isinstance(allp, (list, tuple)):
                    for p in allp:
                        if p is not None:
                            pieces.append(p)

            # examine every detected piece object/string
            for p in pieces:
                if isinstance(p, str):
                    if "king" in p.lower():
                        continue
                    return False
                # object-based piece: try various attributes
                t = None
                for attr in ("type", "kind", "name", "piece_type"):
                    if hasattr(p, attr):
                        t = str(getattr(p, attr))
                        break
                if t:
                    if "king" in t.lower():
                        continue
                    return False
                # final fallback: check class name
                try:
                    if "king" in p.__class__.__name__.lower():
                        continue
                    return False
                except Exception:
                    # if we can't tell what it is, conservatively treat it as non-king
                    return False
            # nothing non-king found
            return True
        except Exception:
            # on unexpected errors, do not claim only-kings (avoid false draws)
            return False
    
    def _only_kings_left(self):
        """
        Return True if the board contains ONLY kings (no other pieces).
        Works for multiple engine data layouts (piece_location dict, piece lists, piece objects).
        """
        try:
            e = getattr(self, "chess", None)
            if not e:
                return False

            pieces = []

            # Common layout: piece_location = { file: { rank: (name, selected, (x,y)) } }
            pl = getattr(e, "piece_location", None)
            if isinstance(pl, dict):
                for f in pl.values():
                    if not isinstance(f, dict):
                        continue
                    for cell in f.values():
                        if not cell:
                            continue
                        # cell may be tuple (name, flag, (x,y)) or simple name
                        if isinstance(cell, (list, tuple)) and len(cell) > 0:
                            name = cell[0]
                        else:
                            name = cell
                        if name:
                            pieces.append(str(name))
            else:
                # fallback to flat lists of piece objects/names
                for attr in ("pieces", "all_pieces", "board_pieces", "piece_list"):
                    allp = getattr(e, attr, None)
                    if isinstance(allp, (list, tuple)):
                        for p in allp:
                            if not p:
                                continue
                            if isinstance(p, str):
                                pieces.append(p)
                            else:
                                # try to extract a name/type attribute
                                for a in ("name", "type", "kind", "piece_type"):
                                    if hasattr(p, a):
                                        v = getattr(p, a)
                                        if v:
                                            pieces.append(str(v))
                                            break
                                else:
                                    pieces.append(p.__class__.__name__)
                        break

            if not pieces:
                # be conservative: if we can't detect pieces, do not claim insufficient material
                return False

            # Every piece must be a king
            for p in pieces:
                try:
                    if "king" not in str(p).lower():
                        return False
                except Exception:
                    return False
            return True
        except Exception:
            return False
        
    def _init_promotion_overlay(self):
        """
        Build self.promotion_overlay from self.chess.promotion_pending.
        Called once when a pending promotion is first seen.
        """
        p = getattr(self.chess, "promotion_pending", None)
        if not p:
            self.promotion_overlay = None
            return

        try:
            color = p["color"]
            file_char = p["file"]
            row_no = p["row"]
            # compute pawn's pixel center using chess data structures
            xy = self.chess.piece_location[file_char][row_no][2]
            bx, by = self.chess.board_locations[xy[0]][xy[1]]
            pawn_center_x = bx + self.square_length // 2
            pawn_top_y = by
        except Exception:
            pawn_center_x = self.screen.get_width() // 2
            pawn_top_y = self.screen.get_height() // 2

        options = ["queen", "rook", "bishop", "knight"]
        icon_size = min(48, max(24, self.square_length))
        padding = 8
        label_height = 20
        width = len(options) * icon_size + (len(options) + 1) * padding
        height = icon_size + label_height + padding * 2

        ox = pawn_center_x - width // 2
        oy = pawn_top_y - height - 8
        if oy < 8:
            oy = pawn_top_y + self.square_length + 8

        rects = []
        for i, opt in enumerate(options):
            rx = ox + padding + i * (icon_size + padding)
            ry = oy + padding + label_height
            rects.append({"opt": opt, "rect": pygame.Rect(int(rx), int(ry), int(icon_size), int(icon_size))})

        self.promotion_overlay = {
            "ox": ox, "oy": oy, "width": width, "height": height,
            "rects": rects, "color": color, "options": options,
            "icon_size": icon_size, "padding": padding, "label_height": label_height
        }

    def _clear_promotion_overlay(self):
        """Clear overlay and engine pending flag after promotion completed or cancelled."""
        try:
            self.promotion_overlay = None
        except Exception:
            pass
        try:
            if hasattr(self.chess, "promotion_pending"):
                self.chess.promotion_pending = None
        except Exception:
            pass


if __name__ == "__main__":
    game = Game()
    game.start_game()