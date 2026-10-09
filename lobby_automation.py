import time
from pathlib import Path

import cv2
from state_finder import get_state
from utils import load_toml_as_dict, config_bool, load_brawlers_info, normalize_brawler_filename, resolve_project_path


class LobbyAutomation:

    def _frame_state(self, frame):
        reader = getattr(type(self.window_controller), 'screen_state', None)
        return reader(self.window_controller, frame) if reader else get_state(frame)

    def __init__(self, window_controller):
        self.gray_pixels_treshold = load_toml_as_dict("./cfg/bot_config.toml").get('idle_pixels_minimum', 500)
        self.idle_reconnect_coords = load_toml_as_dict("cfg/buttons_config.toml")["idle_reconnect"]
        if self.idle_reconnect_coords and isinstance(self.idle_reconnect_coords[0], (int, float)):
            self.idle_reconnect_coords = [self.idle_reconnect_coords]
        self.window_controller = window_controller
        self.verbose_debug = config_bool(load_toml_as_dict("cfg/debug_settings.toml").get('verbose_debug'), False)
        self.idle_disconnect_hsv_high_bounds = load_toml_as_dict("cfg/lobby_config.toml").get("hsv_bounds", {}).get("idle_reconnect_high_bounds", [[10, 22, 42], [10, 22, 90], [118, 66, 46]])

    def check_for_idle(self, frame):
        from disconnect_dialog import idle_disconnect_reload_position
        position = idle_disconnect_reload_position(frame)
        if position is None or time.monotonic() - getattr(self, '_last_idle_reload', 0) < 2:
            return
        # Recheck the current screen: a dialog from a cached frame cannot
        # authorize a click on a lobby that has already appeared.
        position = idle_disconnect_reload_position(self.window_controller.screenshot())
        if position is None:
            return
        self._last_idle_reload = time.monotonic()
        self.window_controller.release_all_inputs()
        self.window_controller.gameplay_frame_time = None
        self.window_controller.click(*position, already_include_ratio=True)


    @staticmethod
    def _should_interrupt(runtime_control=None, stop_event=None):
        if runtime_control and (runtime_control.should_stop() or runtime_control.should_pause()):
            return True
        return stop_event is not None and stop_event.is_set()

    @staticmethod
    def _sleep_interruptible(duration, runtime_control=None, stop_event=None, poll_interval=0.1):
        end_time = time.time() + duration
        while time.time() < end_time:
            if LobbyAutomation._should_interrupt(runtime_control, stop_event):
                return True
            time.sleep(min(poll_interval, max(end_time - time.time(), 0)))
        return False

    def _root_buttons(self):
        """The repository's own buttons_config.toml, read past the device scope."""
        return load_toml_as_dict(resolve_project_path("cfg", "buttons_config.toml"))

    def _button_coordinates(self):
        """Button coordinates for this device, falling back to the root config."""
        merged = dict(self._root_buttons())
        try:
            scoped = load_toml_as_dict("cfg/buttons_config.toml")
        except Exception:  # noqa: BLE001
            scoped = {}
        for key, value in (scoped or {}).items():
            if value:
                merged[key] = value
        missing = [k for k in (
            "brawlers_menu", "brawlers_sort_button", "brawlers_sort_least_trophies",
            "brawlers_first_card", "select_brawler") if not merged.get(k)]
        if missing:
            print(f"Button coordinates missing from both configs: {missing}")
        return merged

    @property
    def last_picked(self):
        """What the game actually put us on: {"brawler": name, "trophies": n}."""
        return getattr(self, "_last_picked", None)

    SORT_LABELS = {
        "brawlers_sort_least_trophies": "Least Trophies",
        "brawlers_sort_closest_to_next_tier": "Closest to Next Tier",
        "brawlers_sort_power_level": "Power Level",
        "brawlers_sort_power_level_low_to_high": "Power Level (low to high)",
        "brawlers_sort_most_trophies": "Most Trophies",
        "brawlers_sort_name": "Name",
    }

    def sort_menu_name(self, sort_point):
        """Which menu entry a coordinate belongs to, by looking it up.

        Comparing coordinates rather than trusting a second argument keeps the
        log honest: if a caller passes the wrong point, the log says what was
        actually pressed instead of what was intended.
        """
        if not sort_point:
            return "brawlers_sort_least_trophies"
        try:
            buttons = load_toml_as_dict("cfg/buttons_config.toml")
        except Exception:  # noqa: BLE001
            return "brawlers_sort_least_trophies"
        wanted = [int(sort_point[0]), int(sort_point[1])]
        for name in self.SORT_LABELS:
            entry = buttons.get(name)
            if not entry:
                continue
            try:
                if [int(entry[0]), int(entry[1])] == wanted:
                    return name
            except (TypeError, ValueError, IndexError):
                continue
        return "brawlers_sort_least_trophies"

    def _known_brawler_names(self):
        """Names that really exist, lower-cased, for checking a card read.

        Cached, because the catalog does not change while the bot runs and this
        sits in a retry loop.
        """
        cached = getattr(self, "_brawler_names_cache", None)
        if cached is not None:
            return cached
        names = set()
        try:
            names = {str(name).strip().lower()
                     for name in (load_brawlers_info() or {})}
        except Exception:  # noqa: BLE001
            names = set()
        # Если каталог недоступен, проверять нечем: пустой набор означает
        # "принимай что прочитано", иначе бот перестал бы выбирать вовсе.
        self._brawler_names_cache = names
        return names

    def select_brawler_by_sort(self, get_latest_state, stop_event=None,
                              runtime_control=None, sort_point=None,
                              card_index=0):
        """Pick a brawler by letting the game sort, then take the first card.

        Every brawler card carries its trophies, its power level and its
        progress to the next tier, but reading 40 of those numbers off the screen
        is the fragile way to do it. The brawler menu sorts by all of it itself -
        "Least Trophies", "Closest to Next Tier", "Power Level (low to high)" -
        so the answer is simply the first card in the list, with no OCR and no
        assumptions about card layout.

        sort_point is the menu entry to choose; None means "Least Trophies",
        which is what this has always done.
        """
        buttons = self._button_coordinates()
        open_menu = buttons.get("brawlers_menu")
        sort_button = buttons.get("brawlers_sort_button")
        least = sort_point or buttons.get("brawlers_sort_least_trophies")
        # self.SORT_LABELS, not the bare name: the table is a class attribute and
        # there is no module-level SORT_LABELS, so the bare form raised NameError
        # the first time a rotation actually reached this line.
        sort_label = self.SORT_LABELS.get(self.sort_menu_name(sort_point),
                                     "Least Trophies")
        # Accept legacy card_index arguments, but always choose the sorted first card.
        index = 0
        first_card = buttons.get("brawlers_card_00") or buttons.get(
            "brawlers_first_card")
        select_button = buttons.get("select_brawler")
        if not all([open_menu, sort_button, least, first_card, select_button]):
            print("Brawler sorting coordinates are missing from buttons_config.toml.")
            return "error"

        def fresh_state():
            return self._frame_state(self.window_controller.screenshot())

        state = fresh_state()
        if state != "lobby":
            print(f"Not in the lobby (state '{state}'), not changing brawler.")
            return "stuck"

        # A single tap can be swallowed: a popup may still be fading, or the
        # lobby may not have finished settling. Retrying a few times is what
        # makes this reliable enough to run unattended.
        opened = False
        for attempt in range(3):
            if self._sleep_interruptible(0.5, runtime_control, stop_event):
                return "aborted"
            if fresh_state() != "lobby":
                return "stuck"
            self.window_controller.click(open_menu[0], open_menu[1], already_include_ratio=False)
            if self._sleep_interruptible(1.5, runtime_control, stop_event):
                return "aborted"
            state = fresh_state()
            if state == "brawler_selection":
                opened = True
                break
            print(f"Brawler menu did not open on attempt {attempt + 1}, "
                   f"state is '{state}'")
        if not opened:
            print("Brawler menu would not open; treating the switch as failed so "
                  "it is retried on the next lobby tick instead of costing a "
                  "whole quota.")
            return "error"

        if fresh_state() != "brawler_selection":
            print("Connection lost dialog is up over the brawler menu; not "
                  "touching the sort so the main loop can dismiss it.")
            return "stuck"

        # The sort persists between visits, so ask for it explicitly rather than
        # trusting whatever the player left selected last time.
        self.window_controller.click(sort_button[0], sort_button[1], already_include_ratio=False)
        if self._sleep_interruptible(0.8, runtime_control, stop_event):
            return "aborted"

        # This check is the whole point. The private server drops the connection
        # in the middle of this sequence often enough to matter, and its dialog
        # covers exactly the rows of the sort list. A click meant for the sort
        # entry lands on the dialog instead, the sort is never applied, and the
        # grid keeps the order it already had - so the same brawler stays first
        # and the rotation looks broken while every log line claims success.
        state = fresh_state()
        if state in ("connection_lost", "idle_disconnect"):
            print("Connection lost dialog is covering the sort list; leaving the "
                  "sort untouched so it can be retried after the dialog closes.")
            return "stuck"
        if state != "brawler_selection":
            print(f"Expected the brawler menu after opening the sort, but the "
                  f"screen is '{state}'; not choosing a sort.")
            return "stuck"

        self.window_controller.click(least[0], least[1], already_include_ratio=False)
        if self._sleep_interruptible(1.6, runtime_control, stop_event):
            return "aborted"

        # Read the card before tapping it. The grid animates after the sort tap,
        # so a single read can land on a half-drawn screen: retry, and keep the
        # frame that failed so a missed read can be looked at instead of guessed.
        self._last_picked = None
        try:
            import cv2

            import trophy_reader

            if trophy_reader.available():
                known = self._known_brawler_names()
                last_seen = ""
                for attempt in range(6):
                    if self._sleep_interruptible(0.8, runtime_control, stop_event):
                        return "aborted"
                    frame = self.window_controller.screenshot()
                    state = self._frame_state(frame)
                    if frame is None:
                        continue
                    from owned_cards import resolved_card
                    _, anchor = resolved_card(frame, first_card)
                    card = trophy_reader.read_card(frame, card_index=index, anchor=anchor)
                    name = str(card.get("brawler") or "").strip().lower()
                    # A read is only believed if the name is a brawler that
                    # exists. Anything else is OCR noise, and acting on it would
                    # write a brawler nobody has into the queue.
                    if name and (not known or name in known):
                        self._last_picked = card
                        print(f"First card under the {sort_label} sort reads as "
                              f"{card['brawler']} with {card.get('trophies')} trophies.")
                        break
                    last_seen = name or "(пусто)"
                    print(f"Card name not usable on attempt {attempt + 1}: "
                          f"{last_seen!r} (state '{state}').")
                    if state != "brawler_selection" and attempt >= 2:
                        Path("debug_shots").mkdir(exist_ok=True)
                        cv2.imwrite(f"debug_shots/card_read_fail_{int(time.time())}.png", frame)
                        break
                else:
                    print(f"Gave up reading the card; last attempt gave {last_seen!r}.")
        except Exception as error:  # noqa: BLE001
            print(f"Reading the lowest-trophy card failed: {error}")

        frame = self.window_controller.screenshot()
        if self._frame_state(frame) != "brawler_selection":
            print("Brawler grid was not confirmed before card selection; no tap sent.")
            return "stuck"
        from owned_cards import resolved_card
        first_card, _ = resolved_card(frame, first_card)
        if self._should_interrupt(runtime_control, stop_event):
            return "aborted"
        self.window_controller.click(first_card[0], first_card[1], already_include_ratio=False)
        if self._sleep_interruptible(1.2, runtime_control, stop_event):
            return "aborted"
        if not self._confirm_brawler_selection(runtime_control, stop_event):
            return "stuck"
        if self._sleep_interruptible(1.5, runtime_control, stop_event):
            return "aborted"

        state = fresh_state()
        if state != "lobby":
            print(f"After picking the lowest trophy brawler the screen is '{state}'.")
            return "stuck"
        picked = self._last_picked or {}
        who = f": {picked['brawler']}" if picked.get("brawler") else (
            ", name not readable from the card")
        print(f"Picked the first card under the {sort_label} sort{who}.")
        return "success"

    def _confirm_brawler_selection(self, runtime_control=None, stop_event=None):
        from brawler_detail import detail_select_position
        for attempt in range(3):
            if self._should_interrupt(runtime_control, stop_event):
                return False
            # Refresh the decision ticket after the grid-to-detail transition.
            # A click using the old grid observation is rightly rejected.
            frame = self.window_controller.screenshot()
            position = detail_select_position(frame)
            if position is not None:
                self.window_controller.click(*position, already_include_ratio=True)
                return True
            if self._sleep_interruptible(.25, runtime_control, stop_event):
                return False
        print("Brawler Select control was not confirmed; leaving recovery to the main loop.")
        return False

    def select_lowest_trophy_brawler(self, get_latest_state, stop_event=None,
                                    runtime_control=None):
        """The original entry point: sort by fewest trophies.

        Kept as a name rather than a second copy of the body, because the four
        call sites in bot_instance and stage_manager all mean exactly this.
        """
        return self.select_brawler_by_sort(
            get_latest_state, stop_event=stop_event,
            runtime_control=runtime_control)

    def select_brawler(self, brawler, get_latest_state, stop_event=None, runtime_control=None):
        brawler = str(brawler).lower().strip()
        normalized_brawler = normalize_brawler_filename(brawler)
        brawler_info = load_brawlers_info().get(normalized_brawler, {})
        brawler_search_name = brawler_info.get("actual_name") or normalized_brawler

        x, y = load_toml_as_dict("cfg/buttons_config.toml")["brawlers_menu"]
        frame = self.window_controller.screenshot()
        if self._frame_state(frame) != 'lobby':
            return 'stuck'
        self.window_controller.click(x, y, already_include_ratio=False)
        if self._sleep_interruptible(1.25, runtime_control, stop_event):
            return 'aborted'
        print("Automatic brawler selection started for", brawler_search_name)
        for i in range(100):
            if self._should_interrupt(runtime_control, stop_event):
                print("Brawler selection aborted by user.")
                return "aborted"
            frame = self.window_controller.screenshot()
            current_state = self._frame_state(frame)
            if current_state == "shop":
                print("Brawler menu is still opening")
                if self._sleep_interruptible(1, runtime_control, stop_event):
                    return 'aborted'
                continue

            if current_state != "brawler_selection":
                print("Latest screenshot is no longer of the lobby, aborting brawler selection...")
                return "stuck"

            self.window_controller.press("brawler_search")
            if self._sleep_interruptible(1, runtime_control, stop_event):
                print("Brawler selection aborted by user.")
                return "aborted"

            if not self.window_controller.type_text(brawler_search_name):
                print(f"Could not enter brawler name '{brawler_search_name}' in the search field.")
                return "error"
            if self._sleep_interruptible(0.5, runtime_control, stop_event):
                print("Brawler selection aborted by user.")
                return "aborted"

            import trophy_reader
            frame=self.window_controller.screenshot()
            if self._frame_state(frame) != 'brawler_selection':return 'stuck'
            card=trophy_reader.read_card(frame,card_index=0)
            if str(card.get('brawler') or '').lower().strip() != normalized_brawler:
                print('Search result did not confirm the requested brawler; no selection tap sent.')
                return 'failed'
            first_brawler_x, first_brawler_y = load_toml_as_dict("cfg/buttons_config.toml")["first_brawler_icon"]
            self.window_controller.click(first_brawler_x, first_brawler_y, already_include_ratio=False)
            if self._sleep_interruptible(1, runtime_control, stop_event):
                print("Brawler selection aborted by user.")
                return "aborted"

            if not self._confirm_brawler_selection(runtime_control, stop_event):
                return "stuck"
            if self._sleep_interruptible(1.5, runtime_control, stop_event):
                print("Brawler selection aborted by user.")
                return "aborted"
            frame=self.window_controller.screenshot()
            if self._frame_state(frame) != 'lobby':return 'stuck'
            self._last_picked = {**card,'brawler':normalized_brawler}
            print("Selected brawler ", brawler_search_name)
            return "success"

        print(f"WARNING: Brawler '{brawler}' was not found after 100 scroll attempts.")
        return "failed"
