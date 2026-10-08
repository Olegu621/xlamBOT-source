import math
import random
import time
import cv2
import numpy as np
import os

from detect import Detect
from utils import load_toml_as_dict, count_hsv_pixels, load_brawlers_info, interpret_playstyle_code, \
    count_mask_pixels, JOYSTICK_RADIUS, clamp, config_bool, is_safe_ast, resolve_project_path


brawl_stars_width, brawl_stars_height = 1920, 1080
super_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['super']
gadget_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['gadget']
hypercharge_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['hypercharge']
POISON_LOW_HSV = np.array((30, 90, 221), dtype=np.uint8)
POISON_HIGH_HSV = np.array((57, 114, 235), dtype=np.uint8)
PLAYER_HIT_CIRCLE_RADIUS = 53
# Escape directions are screen coordinates, so y grows downwards and 90 degrees
# is "down the screen". Eight directions is what the joystick can be steered
# into without a diagonal that slides.
GAS_ESCAPE_ANGLES = tuple(math.radians(angle) for angle in (0, 45, 90, 135, 180, 225, 270, 315))
# Patches sampled along one escape corridor. More samples see a narrow gap
# between two clouds, fewer of them are cheaper but step over it.
GAS_CORRIDOR_SAMPLES = 5
# What counts towards the score from the corridor past gas_reach, up to
# gas_lookahead: a cloud further along the way is worth noticing, but not worth
# as much as one the player is about to walk into.
GAS_FAR_FIELD_WEIGHT = 0.5

from battle_memory import BattleMemory, Steering
from ability_buttons import AbilityButtons

class Play:

    def __init__(self, main_info_model, tile_detector_model, close_tile_detector_model, window_controller, playstyle_code):
        bot_config = load_toml_as_dict("cfg/bot_config.toml")
        time_config = load_toml_as_dict("cfg/time_tresholds.toml")
        self.fix_movement_keys = {
            "delay_to_trigger": bot_config["unstuck_movement_delay"],
            "duration": bot_config["unstuck_movement_hold_time"],
            "toggled": False,
            "started_at": time.time(),
            "fixed": (0, 0),
            "last_direction_key": None,
            "rotation_sign": 1,
            "rotation_angle_step": 1,
            "max_rotation_angle_step": 4,
        }
        self.super_treshold = time_config["super"]
        self.gadget_treshold = time_config["gadget"]
        self.hypercharge_treshold = time_config["hypercharge"]
        self.walls_treshold = time_config["wall_detection"]
        self.last_walls_data = []
        self.last_bushes_data = []
        self.keys_hold = []
        self.time_since_different_movement = time.time()
        self.time_since_gadget_checked = time.time()
        self.is_gadget_ready = False
        self.time_since_hypercharge_checked = time.time()
        self.is_hypercharge_ready = False
        self.time_since_super_checked = time.time()
        self.is_super_ready = False
        self.window_controller = window_controller
        self.TILE_SIZE = bot_config.get("perceived_tile_size", 54)
        self.centered_wall_detection = config_bool(bot_config.get("centered_wall_detection"), False)
        self.centered_wall_crop_size = 640

        bot_config = load_toml_as_dict("cfg/bot_config.toml")
        time_config = load_toml_as_dict("cfg/time_tresholds.toml")
        self.verbose_debug = config_bool(load_toml_as_dict("cfg/debug_settings.toml").get('verbose_debug'), False)
        if self.verbose_debug:
            if not os.path.exists("debug_frames"):
                os.makedirs("debug_frames")
        self.Detect_main_info = Detect(main_info_model, classes=['enemy', 'teammate', 'player'])
        self.tile_detector_model_classes = bot_config["wall_model_classes"]
        self.Detect_tile_detector = None if self.centered_wall_detection else Detect(
            tile_detector_model,
            classes=self.tile_detector_model_classes
        )
        self.Detect_centered_tile_detector = Detect(
            close_tile_detector_model,
            classes=self.tile_detector_model_classes
        ) if self.centered_wall_detection else None

        # Showdown gas is found with a model of its own instead of a colour
        # window: it is a translucent green cloud lying over grass, dirt and
        # water, so no hue range separates it from the map. The model also
        # knows the bushes, so a bush never gets read as a cloud. All of this
        # is optional - with no model file the bot simply plays as if the
        # arena had no gas, and nothing else has to know about it.
        self.gas_model_path = bot_config.get("gas_model", "models/gasDetector.onnx")
        self.gas_classes = bot_config.get("gas_classes", ["gas", "bush"])
        self.gas_confidence = float(bot_config.get("gas_confidence", 0.25))
        self.gas_sensitivity = float(bot_config.get("gas_sensitivity", 0.05))
        self.gas_reach = float(bot_config.get("gas_reach", 3.0))
        self.gas_lookahead = float(bot_config.get("gas_lookahead", 4.0))
        self.gas_detect_interval = float(bot_config.get("gas_detect_interval", 0.2))
        self.gas_escape_cooldown = float(bot_config.get("gas_escape_cooldown", 0.35))
        self.gas_area_top = float(bot_config.get("gas_area_top", 0.21))
        self.gas_area_bottom = float(bot_config.get("gas_area_bottom", 1.0))
        self.gas_danger_enter = float(bot_config.get("gas_danger_enter", 0.14))
        self.gas_danger_exit = float(bot_config.get("gas_danger_exit", 0.05))
        self.gas_centre_bias = float(bot_config.get("gas_centre_bias", 0.06))
        self.gas_avoidance = config_bool(bot_config.get("gas_avoidance"), True)

        self.Detect_gas = None
        gas_model_path = resolve_project_path(self.gas_model_path or "")
        if self.gas_avoidance and self.gas_model_path and os.path.exists(gas_model_path):
            try:
                self.Detect_gas = Detect(str(gas_model_path), classes=self.gas_classes)
            except Exception as error:
                print(f"Gas model could not be loaded, gas avoidance is off: {error}")
        if self.Detect_gas is None:
            print("No gas model loaded, the bot will not look for gas.")

        self.gas_boxes = []
        self.gas_mask = None
        self.gas_mask_time = 0.0
        self.gas_coverage = 0.0
        self.gas_danger = 0.0
        self.gas_in_danger = False
        self.gas_escape_direction = None
        self.gas_escape_index = None
        self.gas_escape_time = 0.0
        self.gas_escapes = 0
        self.gas_danger_escapes = 0
        self.gas_player_box = None
        self.gas_detection_ok = self.Detect_gas is not None or not self.gas_avoidance
        self.gas_observed_at = 0.0
        self.gas_state = 'SAFE'
        self.safety_telemetry = {'override_reason': 'CLASSIC_GAMEPLAY'}
        self.world_state = {}
        self.latency = {}
        self.prevented_gas_entries = 0

        self.time_since_walls_checked = 0
        self.time_since_player_last_found = time.time()
        self.current_brawler = None
        self.brawlers_info = load_brawlers_info()
        self.brawler_ranges = None
        self.time_since_detections = {
            "player": time.time(),
            "enemy": time.time(),
        }
        self.time_since_last_proceeding = time.time()

        self.last_movement = ''
        self.last_movement_change_time = time.time()
        self.minimum_movement_delay = bot_config["minimum_movement_delay"]
        self.no_detection_proceed_delay = time_config["no_detection_proceed"]
        self.gadget_pixels_minimum = bot_config["gadget_pixels_minimum"]
        self.hypercharge_pixels_minimum = bot_config["hypercharge_pixels_minimum"]
        self.super_pixels_minimum = bot_config["super_pixels_minimum"]
        self.wall_detection_confidence = bot_config["wall_detection_confidence"]
        self.entity_detection_confidence = bot_config["entity_detection_confidence"]
        self.seconds_to_hold_attack_after_reaching_max = load_toml_as_dict("cfg/bot_config.toml")["seconds_to_hold_attack_after_reaching_max"]
        self.persistent_data = {"time_since_holding_attack": None}
        if isinstance(playstyle_code, str):
            is_safe, error_msg = is_safe_ast(playstyle_code)
            if not is_safe:
                print(f"Security/Syntax Validation Failed for playstyle: {error_msg}")
                self.playstyle_code = compile("", "<string>", "exec")
            else:
                self.playstyle_code = compile(playstyle_code, "<playstyle>", "exec")
        else:
            self.playstyle_code = playstyle_code
        self.battle_memory = BattleMemory()
        self.steering = Steering()
        from bush_cover import BushCover
        self.bush_cover = BushCover()
        from incoming_damage import IncomingDamage
        self.incoming_damage = IncomingDamage()
        self.ability_buttons = AbilityButtons()
        self.reset_battle_pending = False
        from combat_behavior import CombatBehavior
        self.behavior = CombatBehavior()
        self.behavior_report = {}
        self.work_mode = 2
        self._work_style = None
        self.context = None
        self.frame = None

    @staticmethod
    def get_entity_pos(entity):
        return (entity[0] + entity[2]) / 2, (entity[1] + entity[3]) / 2

    @staticmethod
    def get_distance(enemy_coords, player_coords):
        return math.hypot(enemy_coords[0] - player_coords[0], enemy_coords[1] - player_coords[1])

    @staticmethod
    def is_there_enemy(enemy_data):
        if not enemy_data:
            return False
        return True

    def defensive_target_present(self):
        context = self.context or {}
        player = context.get('player_data')
        if not player:
            return False
        position = self.get_entity_pos(player)
        _, attack_range, _ = self.get_brawler_range(self.current_brawler)
        return any(self.get_distance(position,self.get_entity_pos(e)) <= attack_range*.65
                   for e in context.get('enemy_data',[]))

    def attack(self, touch_up=True, touch_down=True):
        if touch_down and not self.behavior_report.get('fire_allowed', True):
            return False
        if touch_down and self.work_mode == 1 and not self.defensive_target_present():
            return False
        self.window_controller.press("attack", touch_up=touch_up, touch_down=touch_down)

    def use_ability(self, ability):
        # Called only inside a fresh, confirmed gameplay frame, never a menu.
        if self.work_mode == 1 and not self.defensive_target_present():
            return False
        if ability == 'super':
            from super_policy import choose
            player=self.get_entity_pos(self.context['player_data'])
            _,attack_range,super_range=self.get_brawler_range(self.current_brawler)
            if not choose(self.current_brawler,self.brawlers_info[self.current_brawler],self.work_mode,player,self.context['enemy_data'],attack_range,super_range,
                lambda box:self.is_enemy_hittable(player,self.get_entity_pos(box),self.context['walls'],'super')):return False
        target = self.behavior_report.get('target')
        if target is not None and ability != 'super':
            _, attack_range, super_range = self.get_brawler_range(self.current_brawler)
            reach = max(attack_range, super_range) if ability in ('super','hypercharge') else attack_range
            if self.behavior_report.get('target_distance', 0) > reach:
                return False
        point = self.ability_buttons.consume(ability, time.time())
        if point is None:
            return False
        self.window_controller.click(*point, delay=.06, already_include_ratio=True)
        self.ability_buttons.last_action={'ability':ability,'at':time.time(),'point':list(point)}
        setattr(self, 'is_'+ability+'_ready', False)
        setattr(self, 'time_since_'+ability+'_checked', time.time())
        return True

    def use_hypercharge(self):
        return self.use_ability('hypercharge')

    def use_gadget(self):
        return self.use_ability('gadget')

    def use_super(self):
        return self.use_ability('super')

    @staticmethod
    def get_random_movement():
        random_movement = random.randint(-75, 75), random.randint(-75, 75)
        return random_movement

    @staticmethod
    def movement_to_vector(movement):
        if not isinstance(movement, (tuple, list)) or len(movement) != 2:
            return None

        x, y = movement
        if x is None or y is None:
            return None

        try:
            return float(x), float(y)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def rotate_movement(movement, angle_radians):
        x, y = movement
        cos_angle = math.cos(angle_radians)
        sin_angle = math.sin(angle_radians)
        return (
            x * cos_angle - y * sin_angle,
            x * sin_angle + y * cos_angle,
        )

    @staticmethod
    def movement_direction_key(movement):
        x, y = movement
        magnitude = math.hypot(x, y)
        if magnitude < 1:
            return None

        angle = math.atan2(y, x)
        return round(angle / (math.pi / 8)) % 16

    def unstuck_movement_if_needed(self, movement, current_time=None):
        if current_time is None:
            current_time = time.time()

        movement_vector = self.movement_to_vector(movement)
        if movement_vector is None:
            self.fix_movement_keys["toggled"] = False
            self.fix_movement_keys["last_direction_key"] = None
            self.fix_movement_keys["rotation_sign"] = 1
            self.fix_movement_keys["rotation_angle_step"] = 1
            self.time_since_different_movement = current_time
            return movement

        direction_key = self.movement_direction_key(movement_vector)
        if direction_key is None:
            self.fix_movement_keys["toggled"] = False
            self.fix_movement_keys["last_direction_key"] = None
            self.fix_movement_keys["rotation_sign"] = 1
            self.fix_movement_keys["rotation_angle_step"] = 1
            self.time_since_different_movement = current_time
            return movement_vector

        if self.fix_movement_keys['toggled']:
            if current_time - self.fix_movement_keys['started_at'] > self.fix_movement_keys['duration']:
                self.fix_movement_keys['toggled'] = False
                self.fix_movement_keys["last_direction_key"] = direction_key
                self.time_since_different_movement = current_time
                return movement_vector

            return self.fix_movement_keys['fixed']

        if self.fix_movement_keys["last_direction_key"] != direction_key:
            self.fix_movement_keys["last_direction_key"] = direction_key
            self.fix_movement_keys["rotation_sign"] = 1
            self.fix_movement_keys["rotation_angle_step"] = 1
            self.time_since_different_movement = current_time

        if (current_time - self.time_since_different_movement > self.fix_movement_keys["delay_to_trigger"]
                and self.battle_memory.stalled(current_time, self.fix_movement_keys["delay_to_trigger"])):
            self.fix_movement_keys["rotation_sign"] *= -1
            angle_step = self.fix_movement_keys["rotation_angle_step"]
            rotated_movement = self.rotate_movement(
                movement_vector,
                self.fix_movement_keys["rotation_sign"] * angle_step * math.pi / 4
            )
            if self.fix_movement_keys["rotation_sign"] > 0:
                self.fix_movement_keys["rotation_angle_step"] += 1
                if self.fix_movement_keys["rotation_angle_step"] > self.fix_movement_keys["max_rotation_angle_step"]:
                    self.fix_movement_keys["rotation_angle_step"] = 1

            self.fix_movement_keys['fixed'] = rotated_movement
            self.fix_movement_keys['toggled'] = True
            self.fix_movement_keys['started_at'] = current_time
            return rotated_movement

        return movement_vector

    def load_brawler_ranges(self, brawlers_info=None):
        if not brawlers_info:
            brawlers_info = load_brawlers_info()
        screen_size_ratio = self.window_controller.scale_factor
        ranges = {}
        for brawler, info in brawlers_info.items():
            attack_range = info['attack_range']
            safe_range = info['safe_range']
            super_range = info['super_range']
            v = [safe_range, attack_range, super_range]
            ranges[brawler] = [int(v[0] * screen_size_ratio), int(v[1] * screen_size_ratio), int(v[2] * screen_size_ratio)]
        return ranges

    @staticmethod
    def can_attack_through_walls(brawler, skill_type, brawlers_info=None):
        if not brawlers_info: brawlers_info = load_brawlers_info()
        if skill_type == "attack":
            return brawlers_info[brawler]['ignore_walls_for_attacks']
        elif skill_type == "super":
            return brawlers_info[brawler]['ignore_walls_for_supers']
        raise ValueError("skill_type must be either 'attack' or 'super'")

    @staticmethod
    def must_brawler_hold_attack(brawler, brawlers_info=None):
        if not brawlers_info: brawlers_info = load_brawlers_info()
        return brawlers_info[brawler]['hold_attack'] > 0

    @staticmethod
    def walls_block_line_of_sight(p1, p2, walls):
        if not walls:
            return False

        p1_t = (int(p1[0]), int(p1[1]))
        p2_t = (int(p2[0]), int(p2[1]))
        min_x, max_x = min(p1_t[0], p2_t[0]), max(p1_t[0], p2_t[0])
        min_y, max_y = min(p1_t[1], p2_t[1]), max(p1_t[1], p2_t[1])
        for wall in walls:
            x1, y1, x2, y2 = wall

            if max_x < x1 or min_x > x2 or max_y < y1 or min_y > y2:
                continue

            rect = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            if cv2.clipLine(rect, p1_t, p2_t)[0]:
                return True
        return False

    def get_player_hit_circle(self, player_box):
        radius = PLAYER_HIT_CIRCLE_RADIUS * (self.window_controller.scale_factor or 1)
        if player_box and len(player_box) >= 4:
            x1, y1, x2, y2 = player_box[:4]
            return ((x1 + x2) / 2, y2 - radius), radius

        return None, radius

    def get_actual_player_box(self, player_box):
        center, radius = self.get_player_hit_circle(player_box)
        if center is None:
            return None
        return [
            center[0] - radius,
            center[1] - radius,
            center[0] + radius,
            center[1] + radius,
        ]

    @staticmethod
    def point_rect_distance_sq(point, rect):
        x, y = point
        x1, y1, x2, y2 = rect
        dx = max(x1 - x, 0, x - x2)
        dy = max(y1 - y, 0, y - y2)
        return dx * dx + dy * dy

    @staticmethod
    def walls_block_swept_circle(p1, p2, radius, walls):
        from local_navigation import blocked
        return blocked(p1,p2,radius,walls)

    def is_enemy_hittable(self, player_pos, enemy_pos, walls, skill_type):
        if self.can_attack_through_walls(self.current_brawler, skill_type, self.brawlers_info):
            return True
        if self.walls_block_line_of_sight(player_pos, enemy_pos, walls):
            return False
        return True

    def find_closest_enemy(self, enemy_data, player_coords, walls, skill_type):
        player_pos_x, player_pos_y = player_coords
        closest_hittable_distance = float('inf')
        closest_unhittable_distance = float('inf')
        closest_hittable = None
        closest_unhittable = None
        for enemy in enemy_data:
            enemy_pos = self.get_entity_pos(enemy)
            distance = self.get_distance(enemy_pos, player_coords)
            if self.is_enemy_hittable((player_pos_x, player_pos_y), enemy_pos, walls, skill_type):
                if distance < closest_hittable_distance:
                    closest_hittable_distance = distance
                    closest_hittable = [enemy_pos, distance]
            else:
                if distance < closest_unhittable_distance:
                    closest_unhittable_distance = distance
                    closest_unhittable = [enemy_pos, distance]
        if closest_hittable:
            return closest_hittable
        elif closest_unhittable:
            return closest_unhittable

        return None, None

    def find_closest_teammate(self, teammate_data, player_coords, walls):
        closest_distance = float('inf')
        closest_teammate = None
        for teammate in teammate_data:
            teammate_pos = self.get_entity_pos(teammate)
            distance = self.get_distance(teammate_pos, player_coords)
            if distance < closest_distance:
                closest_distance = distance
                closest_teammate = teammate_pos
        return closest_teammate, closest_distance

    def is_there_poison_gas(self, player_data, threshold=7000, area_from_player_checked=1.5):
        """Gas pixels on each side of the player, as up/down/left/right counts.

        Kept for the playstyles and the debug overlay, so the shape of the
        answer never changes: a count of gas pixels in the region around the
        player, or 0 for a side with nothing on it.

        The pixels come from the gas model when one is loaded, because showdown
        gas is green and translucent and a colour window cannot tell it apart
        from the grass under it. Without a model the old colour scan is used, so
        a missing model means "no gas seen" rather than an error.
        """
        mask = self.gas_mask
        if mask is None or self.frame is None or mask.shape[:2] != self.frame.shape[:2]:
            return self.scan_poison_colour(player_data, threshold, area_from_player_checked)

        return self.collect_gas_sides(
            lambda x1, y1, x2, y2: count_mask_pixels(mask, x1, y1, x2, y2),
            player_data,
            threshold,
            area_from_player_checked,
            "Gas model",
            # The model's mask is dense, so a side only a few hundred pixels
            # across never reaches the old 7000 pixel gate. A side also counts
            # as gassed once a real share of it is covered, which keeps the
            # number the playstyles compare meaningful at any resolution.
            min_share=self.gas_sensitivity
        )

    def scan_poison_colour(self, player_data, threshold=7000, area_from_player_checked=1.5):
        """Colour scan for gas, kept for a setup without a gas model.

        The gas in the game is green, not violet, so this window mostly matches
        the map; it is only the fallback now that the model does the work.
        """
        frame = self.frame
        if frame is None:
            return {"up": 0, "down": 0, "left": 0, "right": 0}

        def count_colour(x1, y1, x2, y2):
            roi = frame[y1:y2, x1:x2]
            if roi.size == 0:
                return 0
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
            return count_mask_pixels(
                cv2.inRange(hsv_roi, POISON_LOW_HSV, POISON_HIGH_HSV),
                0, 0, roi.shape[1], roi.shape[0]
            )

        return self.collect_gas_sides(
            count_colour,
            player_data,
            threshold,
            area_from_player_checked,
            "Poison"
        )

    def collect_gas_sides(self, counter, player_data, threshold, area_from_player_checked, label, min_share=None):
        """Split the area around the player into four sides and count gas.

        `counter` is handed frame coordinates and answers with the number of gas
        pixels in that rectangle, which lets the model mask and the colour scan
        share everything except how they find the gas themselves. A side is
        reported when it passes the pixel `threshold`, or - if `min_share` is
        given - when that much of it is covered.
        """
        empty = {"up": 0, "down": 0, "left": 0, "right": 0}

        if not player_data or len(player_data) < 4 or self.frame is None:
            return empty

        actual_player_box = self.get_actual_player_box(player_data) or player_data
        px1, py1, px2, py2 = actual_player_box
        player_width = max(px2 - px1, 1)
        player_height = max(py2 - py1, 1)
        min_x = int(max(px1 - player_width*area_from_player_checked, 0))
        max_x = int(min(px2 + player_width*area_from_player_checked, self.window_controller.width))
        min_y = int(max(py1 - player_height*area_from_player_checked, 0))
        max_y = int(min(py2 + player_height*area_from_player_checked, self.window_controller.height))

        if min_x >= max_x or min_y >= max_y:
            return empty

        x, y = self.get_entity_pos(actual_player_box)
        roi_w = int(max_x - min_x)
        roi_h = int(max_y - min_y)
        local_px = int(clamp(x - min_x, 0, roi_w))
        local_py = int(clamp(y - min_y, 0, roi_h))

        areas = {
            "up": roi_w * local_py,
            "down": roi_w * (roi_h - local_py),
            "left": local_px * roi_h,
            "right": (roi_w - local_px) * roi_h,
        }

        counts = {
            "up": counter(min_x, min_y, max_x, min_y + local_py),
            "down": counter(min_x, min_y + local_py, max_x, max_y),
            "left": counter(min_x, min_y, min_x + local_px, max_y),
            "right": counter(min_x + local_px, min_y, max_x, max_y),
        }

        result = {}
        for direction, count in counts.items():
            gassed = count > threshold
            if not gassed and min_share is not None and areas[direction] > 0:
                gassed = count / areas[direction] > min_share
            result[direction] = count if gassed else 0

        if self.verbose_debug:
            print(f"{label} gas pixels:", counts)

            ts = int(time.time())

            roi = self.frame[min_y:max_y, min_x:max_x]
            debug_regions = {
                "up": roi[0:local_py, 0:roi_w],
                "down": roi[local_py:roi_h, 0:roi_w],
                "left": roi[0:roi_h, 0:local_px],
                "right": roi[0:roi_h, local_px:roi_w],
            }

            for direction, img in debug_regions.items():
                if img.size > 0:
                    cv2.imwrite(
                        f"debug_frames/poison_gas_{direction}_debug_{ts}.png",
                        cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                    )

        return result

    def detect_gas(self, image):
        """Run the gas model over a frame and keep the clouds it found.

        Fills `gas_boxes` with the clouds inside the play area and `gas_mask`
        with their union. The whole frame goes to the model on purpose: the
        model brings its own clouds, so there is no pixel count to threshold and
        nothing at all to keep when the arena is clean.

        The model also flags the dark tree band above the arena, so clouds whose
        middle sits above `gas_area_top` (or below `gas_area_bottom`) are
        dropped. Cutting that band took 20 false clouds on the trees down to 0.
        """
        self.gas_boxes = []
        self.gas_mask = None
        self.gas_mask_time = time.time()

        if self.Detect_gas is None or image is None or getattr(image, "size", 0) == 0:
            self.gas_detection_ok = False
            return self.gas_boxes

        try:
            detections = self.Detect_gas.detect_objects(image, conf_tresh=self.gas_confidence)
        except Exception as error:
            import error_telemetry
            error_telemetry.report('gas_detector_failed', 'error', error,
                                   device=getattr(getattr(self, 'window_controller', None), 'serial', None), stage='model')
            print(f"Gas detection failed: {error}")
            self.gas_detection_ok = False
            self._gas_retry_at = time.time() + 1
            return self.gas_boxes

        height = image.shape[0]
        top_limit = self.gas_area_top * height
        bottom_limit = self.gas_area_bottom * height

        boxes = []
        for box in (detections or {}).get("gas", []):
            if not box or len(box) < 4:
                continue
            x1, y1, x2, y2 = [float(value) for value in box[:4]]
            middle = (y1 + y2) / 2
            if middle < top_limit or middle > bottom_limit:
                continue
            boxes.append([int(x1), int(y1), int(x2), int(y2)])

        self.gas_boxes = boxes
        self.gas_mask = self.build_gas_mask(image, boxes)
        self.gas_detection_ok = True
        self._gas_retry_at = 0
        self.gas_observed_at = self.gas_mask_time

        return self.gas_boxes

    @staticmethod
    def build_gas_mask(image, boxes):
        """Flatten gas boxes into one 0/255 mask the size of the frame."""
        height, width = image.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)

        for box in boxes or []:
            # Each pair is clamped and put in order on its own: sorting all four
            # together would mix the x and the y of a box into a different one.
            if len(box) < 4 or not all(math.isfinite(float(v)) for v in box[:4]):
                continue
            x1, y1, x2, y2 = [int(value) for value in box[:4]]
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            x1, x2 = max(0, min(width, x1)), max(0, min(width, x2))
            y1, y2 = max(0, min(height, y1)), max(0, min(height, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            mask[y1:y2, x1:x2] = 255

        return mask

    def gas_mask_is_usable(self, image):
        """True when the mask in hand belongs to this frame."""
        if self.gas_mask is None or image is None or getattr(image, "ndim", 0) < 2:
            return False
        return self.gas_mask.shape[:2] == image.shape[:2]

    def gas_share_on_player(self, mask, player_box):
        """Share of the player's body (0..1) that the gas mask covers."""
        if mask is None or not player_box or len(player_box) < 4:
            return 0.0

        box = self.get_actual_player_box(player_box) or player_box
        x1, y1, x2, y2 = [float(value) for value in box[:4]]
        height, width = mask.shape[:2]
        # Rounded before the area is taken: the pixel counter works on whole
        # pixels, so measuring a fractional box would report over 1.0.
        x1 = int(clamp(x1, 0, width))
        x2 = int(clamp(x2, 0, width))
        y1 = int(clamp(y1, 0, height))
        y2 = int(clamp(y2, 0, height))

        area = (x2 - x1) * (y2 - y1)
        if area <= 0:
            return 0.0

        return min(1.0, count_mask_pixels(mask, x1, y1, x2, y2) / area)

    def gas_on_player(self, image, player_box):
        """Share of the player standing in gas, stored in `gas_coverage`.

        This is the number the danger latch and the panel both read. With no
        model, no mask or no player to measure there is nothing to cover, so the
        answer is 0.
        """
        self.refresh_gas(image, player_box)
        return self.gas_coverage

    def refresh_gas(self, image, player_box=None, force=False):
        """Bring the gas state of this frame up to date.

        The model is the expensive half, so it only runs once every
        `gas_detect_interval` seconds. The cheap half - how much of the player
        the mask covers, and whether that counts as standing in gas - is worked
        out from the mask that is already there on every call, so the reading is
        never half a second behind the joystick.
        """
        now = time.time()

        if now < getattr(self, '_gas_retry_at', 0):
            self.gas_state = 'UNAVAILABLE'
            return

        if self.Detect_gas is None or image is None or getattr(image, "size", 0) == 0:
            self.gas_detection_ok = False
            self.clear_gas_state()
            return

        if player_box and len(player_box) >= 4:
            self.gas_player_box = [float(value) for value in player_box[:4]]

        interval = self.gas_detect_interval
        if self.gas_boxes:
            # A cloud boundary moves with the camera. Reusing it for several
            # decisions is unsafe even though the frame dimensions are unchanged.
            interval = min(interval, .1)
        if force or not self.gas_mask_is_usable(image) or now - self.gas_mask_time >= interval:
            self.detect_gas(image)

        if self.gas_player_box and self.gas_mask is not None:
            self.gas_coverage = self.gas_share_on_player(self.gas_mask, self.gas_player_box)
        else:
            self.gas_coverage = 0.0

        if not self.gas_detection_ok:
            self.gas_state = 'UNAVAILABLE'
            return
        self.update_gas_danger(self.gas_coverage)

        if self.verbose_debug:
            print(
                f"Gas: {len(self.gas_boxes)} cloud(s), "
                f"coverage {self.gas_coverage:.3f}, danger {self.gas_danger:.3f}"
            )

    def clear_gas_state(self):
        """Forget the gas reading, for when there is nothing to measure.

        Called when the player cannot be found: a coverage from a player that
        is no longer on screen would keep the panel showing danger forever.
        """
        self.gas_boxes = []
        self.gas_mask = None
        self.gas_player_box = None
        self.gas_coverage = 0.0
        self.gas_escape_direction = None
        self.gas_escape_index = None
        self.update_gas_danger(0.0)

    def update_gas_danger(self, coverage):
        """Latch "the player is standing in gas" with hysteresis.

        Showdown gas comes as scattered patches, so running on the first sign of
        it made the bot thrash and never fight. The flight starts once
        `gas_danger_enter` of the body is covered and only ends after the share
        drops back to `gas_danger_exit`, so the edge of a patch no longer flips
        the bot back and forth.
        """
        if self.gas_in_danger:
            self.gas_in_danger = coverage > self.gas_danger_exit
        else:
            self.gas_in_danger = coverage > self.gas_danger_enter

        self.gas_danger = coverage if self.gas_in_danger else 0.0
        return self.gas_in_danger

    def is_in_gas(self):
        """True while the player is standing in gas, hysteresis latch included."""
        return bool(self.gas_in_danger)

    def map_centre(self, image=None):
        """Middle of the arena, in the coordinates the boxes are in."""
        if image is not None and getattr(image, "ndim", 0) >= 2:
            height, width = image.shape[:2]
            return width / 2, height / 2
        width = self.window_controller.width or brawl_stars_width
        height = self.window_controller.height or brawl_stars_height
        return width / 2, height / 2

    def gas_direction_share(self, mask, x, y, player_width, player_height, direction_x, direction_y, reach, start=0.0):
        """Gas share inside the corridor the player would walk down.

        The corridor starts at the edge of the body and runs `reach` player
        widths out, sampled in a few patches so a narrow gap between two clouds
        still shows up. `start` is the share of it to leave out, which is how
        the far end of the corridor is measured on its own. Samples outside the
        frame are dropped and the rest is averaged, so a direction that runs off
        the side of the screen is not punished for the part that was never on it.
        """
        if mask is None or reach <= 0:
            return 0.0

        height, width = mask.shape[:2]
        body = max(player_width, player_height) / 2
        start_x = x + direction_x * body
        start_y = y + direction_y * body
        reach_x = player_width * reach
        reach_y = player_height * reach
        patch = body * 0.6

        gas_pixels = 0
        measured = 0

        for step in range(GAS_CORRIDOR_SAMPLES):
            along = start + (step + 0.5) / GAS_CORRIDOR_SAMPLES * (1.0 - start)
            sample_x = start_x + direction_x * reach_x * along
            sample_y = start_y + direction_y * reach_y * along
            x1 = clamp(sample_x - patch / 2, 0, width)
            x2 = clamp(sample_x + patch / 2, 0, width)
            y1 = clamp(sample_y - patch / 2, 0, height)
            y2 = clamp(sample_y + patch / 2, 0, height)
            if x1 >= x2 or y1 >= y2:
                continue
            measured += (x2 - x1) * (y2 - y1)
            gas_pixels += count_mask_pixels(mask, x1, y1, x2, y2)

        if measured <= 0:
            return 0.0

        return gas_pixels / measured

    @staticmethod
    def gas_direction_index(direction):
        """Which of the eight escape directions a vector points at."""
        if not direction:
            return None
        angle = math.atan2(direction[1], direction[0])
        return int(round(angle / (math.pi / 4))) % len(GAS_ESCAPE_ANGLES)

    def _clearest_escape(self, mask, player_box, walls=None):
        """The least gassy of the eight directions around the player.

        Every direction is scored by the gas share of the corridor it walks
        down, minus a bonus for pointing back at the middle of the map: showdown
        gas does more damage the further out the player is, so a clean step
        inwards beats an equally clean step sideways. Shares under
        `gas_sensitivity` count as clean, which lets that bonus decide between
        two sides instead of a few stray pixels. A side the player cannot walk
        into because of a wall is pushed to the back of the queue.

        Returns a unit (x, y) vector in screen coordinates, or None when there is
        nothing to measure.
        """
        if mask is None or not player_box or len(player_box) < 4:
            return None

        box = self.get_actual_player_box(player_box) or player_box
        player_width = max(box[2] - box[0], 1)
        player_height = max(box[3] - box[1], 1)
        centre_x, centre_y = self.get_entity_pos(box)

        centre = self.map_centre()
        to_centre_x = centre[0] - centre_x
        to_centre_y = centre[1] - centre_y
        distance_to_centre = math.hypot(to_centre_x, to_centre_y)
        if distance_to_centre > 0:
            to_centre_x /= distance_to_centre
            to_centre_y /= distance_to_centre
        else:
            to_centre_x, to_centre_y = 0.0, 0.0

        best_direction = None
        best_score = None
        far_start = self.gas_reach / self.gas_lookahead if self.gas_lookahead > 0 else 0.0

        for angle in GAS_ESCAPE_ANGLES:
            direction_x = math.cos(angle)
            direction_y = math.sin(angle)
            # Two bands: the ground under the next `gas_reach` player widths,
            # and everything up to `gas_lookahead`, which only gets half the
            # weight. A side that is clear now but has a cloud waiting at the
            # end of it is still worse than one that stays clear.
            share = self.gas_direction_share(
                mask, centre_x, centre_y, player_width, player_height,
                direction_x, direction_y, self.gas_reach
            )
            if self.gas_lookahead > self.gas_reach:
                share += GAS_FAR_FIELD_WEIGHT * self.gas_direction_share(
                    mask, centre_x, centre_y, player_width, player_height,
                    direction_x, direction_y, self.gas_lookahead, far_start
                )
            if share < self.gas_sensitivity:
                share = 0.0
            inward = max(0.0, direction_x * to_centre_x + direction_y * to_centre_y)
            score = share - self.gas_centre_bias * inward
            if walls and self.is_path_blocked(player_box, (direction_x, direction_y), walls):
                score += 1.0
            if best_score is None or score < best_score:
                best_score = score
                best_direction = (direction_x, direction_y)

        return best_direction

    def _toward_centre(self, player_box, image=None):
        """Unit vector from the player to the middle of the arena.

        Gas damage grows with the distance from the centre, so when no side is
        clear at all, the way inwards is still the way that hurts least.
        """
        if not player_box or len(player_box) < 4:
            return None

        centre_x, centre_y = self.map_centre(image)
        player_x, player_y = self.get_entity_pos(player_box)
        dx = centre_x - player_x
        dy = centre_y - player_y
        length = math.hypot(dx, dy)
        if length < 1:
            return None

        return dx / length, dy / length

    def avoid_gas(self, image=None, player_box=None, walls=None, current_time=None):
        """Movement that walks the player out of the gas, or None for none.

        A direction is only picked while the player is actually in gas (see
        `update_gas_danger`); the rest of the time this returns None and the
        playstyle's own movement is used untouched. Inside a cloud the eight
        directions are scored as in `_clearest_escape`, and the winner is held
        for `gas_escape_cooldown` so the joystick is not rubbed between two
        neighbouring directions every frame.
        """
        if image is None:
            image = self.frame
        if player_box is None:
            player_box = self.gas_player_box
        if current_time is None:
            current_time = time.time()

        self.refresh_gas(image, player_box)

        if not self.gas_in_danger:
            self.gas_escape_direction = None
            self.gas_escape_index = None
            return None

        direction = self._clearest_escape(self.gas_mask, player_box, walls)
        if direction is None:
            direction = self._toward_centre(player_box, image)
        if direction is None:
            return None

        index = self.gas_direction_index(direction)
        previous = self.gas_escape_direction

        if previous is not None and index != self.gas_escape_index and \
                current_time - self.gas_escape_time < self.gas_escape_cooldown:
            box = self.get_actual_player_box(player_box) or player_box
            from gas_guard import corridor_peak
            old_risk = corridor_peak(self.gas_mask, box, previous, self.gas_lookahead)
            new_risk = corridor_peak(self.gas_mask, box, direction, self.gas_lookahead)
            if not self.is_path_blocked(player_box, previous, walls or []) and old_risk <= new_risk + .05:
                return previous

        if previous is None or index != self.gas_escape_index:
            self.gas_escape_index = index
            self.gas_escape_time = current_time
            self.gas_escapes += 1
            if self.gas_in_danger:
                self.gas_danger_escapes += 1

        self.gas_escape_direction = direction
        return direction

    def get_main_data(self, frame):
        data = self.Detect_main_info.detect_objects(frame, conf_tresh=self.entity_detection_confidence)
        return data

    def is_path_blocked(self, player_box, move_direction, walls, distance=None):
        if distance is None:
            distance = self.TILE_SIZE*self.window_controller.scale_factor*.45
        movement = self.movement_to_vector(move_direction)
        if movement is None:
            return False

        magnitude = math.hypot(movement[0], movement[1])
        if magnitude < 1:
            return False

        dx = movement[0] / magnitude * distance
        dy = movement[1] / magnitude * distance
        hit_circle_center, hit_circle_radius = self.get_player_hit_circle(player_box)
        if hit_circle_center is None:
            return False

        new_pos = (hit_circle_center[0] + dx, hit_circle_center[1] + dy)
        return self.walls_block_swept_circle(hit_circle_center, new_pos, hit_circle_radius, walls)

    @staticmethod
    def validate_game_data(data):
        incomplete = False
        if not data.get("player"):
            incomplete = True  # This is required so track_no_detections can also keep track if enemy is missing

        if "enemy" not in data.keys():
            data['enemy'] = []

        if "teammate" not in data.keys():
            data['teammate'] = []

        if 'wall' not in data.keys() or not data['wall']:
            data['wall'] = []

        if 'bush' not in data.keys() or not data['bush']:
            data['bush'] = []

        return False if incomplete else data

    def track_no_detections(self, data):
        if not data:
            data = {
                "enemy": None,
                "player": None
            }
        for key in self.time_since_detections:
            if key in data and data[key]:
                self.time_since_detections[key] = time.time()

    def do_movement(self, movement):
        movement_vector = self.movement_to_vector(movement)
        if movement_vector is None or math.hypot(*movement_vector) < 1e-9:
            self.window_controller.release_movement()
            return
        self.window_controller.move(*movement_vector)

    def get_brawler_range(self, brawler):
        if self.brawler_ranges is None:
            self.brawler_ranges = self.load_brawler_ranges(self.brawlers_info)
        return self.brawler_ranges.get(brawler, (0, 0, 0))

    @staticmethod
    def normalize_move(x, y, radius=JOYSTICK_RADIUS):
        length = math.hypot(x, y)
        if length <= 0:
            return (0.0, 0.0)
        scale = radius / length
        return (x * scale, y * scale)

    def clamp_movement(self, movement):
        x, y = movement
        length = math.hypot(x, y)
        if length <= 0:
            return (0.0, 0.0)
        scale = JOYSTICK_RADIUS / length
        target_x = x * scale * self.window_controller.width_ratio
        target_y = y * scale * self.window_controller.height_ratio
        return target_x, target_y

    def loop(self, brawler, data, current_time, gas_movement=None):
        from gas_guard import coverage_integral
        mask = self.gas_mask
        self._decision_gas_integral = (mask, coverage_integral(mask)) if mask is not None else None
        try:
            return self._loop_decision(brawler, data, current_time, gas_movement)
        finally:
            # No mask summary survives a decision, including an exception.
            self._decision_gas_integral = None

    def _loop_decision(self, brawler, data, current_time, gas_movement=None):
        decision_started = time.perf_counter()
        self.context = {
                'player_data': data['player'][0],
                'enemy_data': data['enemy'],
                'teammate_data': self.battle_memory.active_allies(data['teammate'], current_time, self.TILE_SIZE*self.window_controller.scale_factor),
                'brawler': brawler,
                'walls': data['wall'],
                'bushes': data['bush'],
                'brawlers_info': self.brawlers_info,
                'must_brawler_hold_attack': self.must_brawler_hold_attack,
                'is_gadget_ready': self.is_gadget_ready,
                'is_hypercharge_ready': self.is_hypercharge_ready,
                'is_super_ready': self.is_super_ready,
                'TILE_SIZE': self.TILE_SIZE*self.window_controller.scale_factor,
                'get_entity_pos': self.get_entity_pos,
                'get_distance': self.get_distance,
                'get_actual_player_box': self.get_actual_player_box,
                'get_brawler_range': self.get_brawler_range,
                'is_there_enemy': self.is_there_enemy,
                'attack': self.attack,
                'use_hypercharge': self.use_hypercharge,
                'use_super': self.use_super,
                'use_gadget': self.use_gadget,
                'get_random_movement': self.get_random_movement,
                'current_brawler': self.current_brawler,
                'last_movement': self.last_movement,
                'last_movement_change_time': self.last_movement_change_time,
                'seconds_to_hold_attack_after_reaching_max': self.seconds_to_hold_attack_after_reaching_max,
                "width": brawl_stars_width,
                "height": brawl_stars_height,
                'find_closest_enemy': self.find_closest_enemy,
                'find_closest_teammate': self.find_closest_teammate,
                'is_there_poison_gas': self.is_there_poison_gas,
                'avoid_gas': self.avoid_gas,
                'is_in_gas': self.is_in_gas,
                'gas_coverage': self.gas_coverage,
                'gas_danger': self.gas_danger,
                'gas_boxes': self.gas_boxes,
                'is_path_blocked': self.is_path_blocked,
                'is_enemy_hittable': self.is_enemy_hittable,
                'time': time,
                'random': random,
                "persistent_data": self.persistent_data,
                'debug': self.verbose_debug,
                'JOYSTICK_RADIUS': JOYSTICK_RADIUS,
                'rotate_movement': self.rotate_movement,
                'normalize_move': self.normalize_move,
                'width_ratio': self.window_controller.width_ratio,
                'height_ratio': self.window_controller.height_ratio
            }
        movement = self.get_movement()
        movement_vector = self.movement_to_vector(movement)
        gas_vector = self.movement_to_vector(gas_movement)
        if movement_vector is None and gas_vector is None:
            self.window_controller.release_movement()
            self.last_movement = ''
            return None
        # Standing in a cloud is worth leaving whatever the playstyle wanted, so
        # the escape takes the joystick immediately without direction debounce.
        movement = self.clamp_movement(gas_vector if gas_vector is not None else movement_vector)
        if gas_vector is None and math.hypot(*movement)<1e-6:
            self.steering.previous = None
            self.fix_movement_keys['toggled'] = False
        elif gas_vector is None:
            movement = self.remembered_movement(movement, data, current_time)
            movement = self.steering.choose(movement, current_time,
                lambda v: self.safe_memory_step(v, data['player'][0], data['wall']))
            if not (self.work_mode == 1 and self.behavior_report.get('intent') == 'hide'):
                movement = self.unstuck_movement_if_needed(movement, current_time)
            # Unstick and held directions must pass the same current gas/wall check.
            if not self.safe_memory_step(movement, data['player'][0], data['wall']):
                movement = self.remembered_movement(movement, data, current_time)
        else:
            movement = self.remembered_movement(movement, data, current_time, escaping=True)
            self.steering.previous = None
            self.fix_movement_keys['toggled'] = False
        self.last_movement = movement
        self.last_movement_change_time = self.steering.changed
        self.latency['decision_ms'] = (time.perf_counter()-decision_started)*1000
        self.safety_telemetry = {
            'desired': movement_vector,
            'final': movement,
            'override_reason': 'CLASSIC_GAS_ESCAPE' if gas_vector is not None else 'CLASSIC_GAMEPLAY',
        }
        return movement

    def safe_memory_step(self, vector, player_box, walls):
        v = self.movement_to_vector(vector)
        if v is None or math.hypot(*v)<1e-6:
            return True
        if self.is_path_blocked(player_box, v, walls):
            return False
        if self.gas_mask is not None:
            actual = self.get_actual_player_box(player_box) or player_box
            x,y = self.get_entity_pos(actual)
            length = math.hypot(*v)
            share = self.gas_direction_share(self.gas_mask,x,y,max(actual[2]-actual[0],1),
                max(actual[3]-actual[1],1),v[0]/length,v[1]/length,self.gas_reach)
            from gas_guard import corridor_peak
            summary = getattr(self, '_decision_gas_integral', None)
            integral = summary[1] if summary is not None and summary[0] is self.gas_mask else None
            peak = corridor_peak(self.gas_mask, actual, v, self.gas_reach, integral=integral)
            if share >= self.gas_sensitivity or peak >= .20:
                self.prevented_gas_entries = getattr(self, 'prevented_gas_entries', 0) + 1
                return False
        return True

    def remembered_movement(self, movement, data, now, escaping=False):
        if not movement or math.hypot(*movement)<1e-6:
            return movement
        tile = self.TILE_SIZE*self.window_controller.scale_factor
        allies = self.battle_memory.active_allies(data['teammate'], now, tile)
        player = self.get_entity_pos(data['player'][0])
        length = math.hypot(*movement)
        unit = (movement[0]/length,movement[1]/length)
        if not escaping and not self.battle_memory.dangers and self.safe_memory_step(movement,data['player'][0],data['wall']):
            return movement
        from local_navigation import detour
        from thinking_levels import PROFILES
        center,radius=self.get_player_hit_circle(data['player'][0])
        def route_risk(point):
            if self.gas_mask is None:return 0.
            h,w=self.gas_mask.shape[:2];x,y=map(int,point)
            if not (0<=x<w and 0<=y<h):return 8.
            patch=self.gas_mask[max(0,y-3):min(h,y+4),max(0,x-3):min(w,x+4)]
            return 5*float((patch>0).mean())
        cached=getattr(self,'navigation_route',None)
        if cached and now<cached[0] and sum(a*b for a,b in zip(unit,cached[1]))>.8 and not self.is_path_blocked(data['player'][0],cached[2],data['wall']):
            route=cached[2]
        else:
            route=detour(center,movement,radius,tile,data['wall'],PROFILES.get(getattr(self,'thinking_level','standard'),PROFILES['standard'])['directions'],risk=route_risk)
            self.navigation_route=(now+.15,unit,route) if route else None
        options = [self.clamp_movement(route)] if route else []
        options += [movement]+[self.clamp_movement((math.cos(a),math.sin(a))) for a in GAS_ESCAPE_ANGLES]
        candidates = []
        for v in options:
            if self.is_path_blocked(data['player'][0],v,data['wall']) if escaping else not self.safe_memory_step(v,data['player'][0],data['wall']):
                continue
            size = math.hypot(*v)
            direction = (v[0]/size,v[1]/size)
            cost = 1-sum(a*b for a,b in zip(unit,direction))
            if escaping and self.gas_mask is not None:
                actual=self.get_actual_player_box(data['player'][0]) or data['player'][0]
                x,y=self.get_entity_pos(actual)
                cost += 8*self.gas_direction_share(self.gas_mask,x,y,max(actual[2]-actual[0],1),max(actual[3]-actual[1],1),direction[0],direction[1],self.gas_reach)
            if route and v == options[0]: cost -= 1.5
            from work_modes import danger_weight
            cost += danger_weight(self.work_mode)*self.battle_memory.score(player,direction,allies,now,tile)
            candidates.append((cost,v))
        return min(candidates,key=lambda c:c[0])[1] if candidates else (0.,0.)

    def check_if_hypercharge_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(hypercharge_crop_area[0] * wr), int(hypercharge_crop_area[1] * hr)
        x2, y2 = int(hypercharge_crop_area[2] * wr), int(hypercharge_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        purple_pixels = count_hsv_pixels(screenshot, (137, 158, 159), (179, 255, 255), self.window_controller)
        if self.verbose_debug:
            print("hypercharge purple pixels:", purple_pixels, "(if > ", self.hypercharge_pixels_minimum, " then hypercharge is ready)")
            try:
                cv2.imwrite(f"debug_frames/hypercharge_debug_{purple_pixels}_{int(time.time())}.png", cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))
            except Exception:
                pass

        if purple_pixels > self.hypercharge_pixels_minimum:
            return True
        return False

    def check_if_gadget_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(gadget_crop_area[0] * wr), int(gadget_crop_area[1] * hr)
        x2, y2 = int(gadget_crop_area[2] * wr), int(gadget_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        green_pixels = count_hsv_pixels(screenshot, (57, 219, 165), (62, 255, 255), self.window_controller)
        if self.verbose_debug:
            print("gadget green pixels:", green_pixels, "(if > ", self.gadget_pixels_minimum, " then gadget is ready)")
            try:
                cv2.imwrite(f"debug_frames/gadget_debug_{green_pixels}_{int(time.time())}.png", cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))
            except Exception:
                pass

        if green_pixels > self.gadget_pixels_minimum:
            return True
        return False

    def check_if_super_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(super_crop_area[0] * wr), int(super_crop_area[1] * hr)
        x2, y2 = int(super_crop_area[2] * wr), int(super_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        yellow_pixels = count_hsv_pixels(screenshot, (17, 170, 200), (27, 255, 255), self.window_controller)
        if self.verbose_debug:
            print("super yellow pixels:", yellow_pixels, "(if > ", self.super_pixels_minimum, " then super is ready)")
            try:
                cv2.imwrite(f"debug_frames/super_debug_{yellow_pixels}_{int(time.time())}.png", cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))
            except Exception:
                pass

        if yellow_pixels > self.super_pixels_minimum:
            return True
        return False

    def get_centered_wall_crop(self, frame, player_data=None):
        frame_height, frame_width = frame.shape[:2]
        crop_size = self.centered_wall_crop_size

        if player_data:
            center_x, center_y = self.get_entity_pos(player_data[0])
        else:
            center_x, center_y = frame_width / 2, frame_height / 2

        crop_x1 = int(clamp(round(center_x - crop_size / 2), 0, frame_width - crop_size))
        crop_y1 = int(clamp(round(center_y - crop_size / 2), 0, frame_height - crop_size))
        crop_x2 = crop_x1 + crop_size
        crop_y2 = crop_y1 + crop_size

        return frame[crop_y1:crop_y2, crop_x1:crop_x2], crop_x1, crop_y1

    @staticmethod
    def offset_tile_data(tile_data, offset_x, offset_y):
        if not offset_x and not offset_y:
            return tile_data

        offset_data = {}
        for class_name, boxes in tile_data.items():
            offset_data[class_name] = [
                [box[0] + offset_x, box[1] + offset_y, box[2] + offset_x, box[3] + offset_y]
                for box in boxes
            ]
        return offset_data

    def get_tile_data(self, frame, player_data=None):
        if self.centered_wall_detection and self.Detect_centered_tile_detector is not None:
            crop, offset_x, offset_y = self.get_centered_wall_crop(frame, player_data)
            tile_data = self.Detect_centered_tile_detector.detect_objects(
                crop,
                conf_tresh=self.wall_detection_confidence
            )
            return self.offset_tile_data(tile_data, offset_x, offset_y)

        tile_data = self.Detect_tile_detector.detect_objects(frame, conf_tresh=self.wall_detection_confidence)
        return tile_data

    def process_tile_data(self, tile_data):
        walls = []
        bushes = []
        for class_name, boxes in tile_data.items():
            if 'bush' not in class_name:
                walls.extend(boxes)
            else:
                bushes.extend(boxes)
        return walls, bushes

    def get_movement(self):
        player = self.get_entity_pos(self.context['player_data'])
        safe_range, attack_range, _ = self.get_brawler_range(self.current_brawler)
        plan = self.behavior.plan(self.work_mode,player,self.context['enemy_data'],
            self.context['teammate_data'],attack_range,safe_range,
            self.TILE_SIZE*self.window_controller.scale_factor,JOYSTICK_RADIUS,time.time(),
            lambda box:self.is_enemy_hittable(player,self.get_entity_pos(box),self.context['walls'],'attack'))
        if self.work_mode == 1:
            player = self.get_player_hit_circle(self.context['player_data'])[0] or player
            tile = self.TILE_SIZE*self.window_controller.scale_factor
            def safe_cover(point, margin):
                if self.gas_mask is None:return True
                h,w=self.gas_mask.shape[:2]
                x,y=point
                patch=self.gas_mask[max(0,int(y-margin)):min(h,int(y+margin)+1),max(0,int(x-margin)):min(w,int(x+margin)+1)]
                return patch.size>0 and (patch>0).mean()<self.gas_sensitivity
            plan=self.bush_cover.plan(player,self.context.get('bushes',[]),self.context['enemy_data'],tile,JOYSTICK_RADIUS,time.time(),attack_range,
                lambda box:self.is_enemy_hittable(player,self.get_entity_pos(box),self.context['walls'],'attack'),safe_cover,attacked=self.incoming_damage.observe(self.frame,self.context['player_data'],time.time()),refuge=self.map_centre(),offset=self.battle_memory.offset)
        self.behavior_report = plan['report']
        if not self.behavior_report['fire_allowed'] and self.persistent_data['time_since_holding_attack'] is not None:
            self.attack(touch_up=True,touch_down=False)
            self.persistent_data['time_since_holding_attack'] = None
        execution = dict(self.context)
        if plan['target'] is not None:execution['enemy_data'] = [plan['target']]
        movement, updated_globals = interpret_playstyle_code(self.playstyle_code, execution)
        self.try_ready_super()
        return movement if plan['movement'] is None else plan['movement']

    def try_ready_super(self):
        if not self.is_super_ready or self.persistent_data['time_since_holding_attack'] is not None:
            return False
        from super_policy import choose
        player=self.get_entity_pos(self.context['player_data'])
        safe,attack_range,super_range=self.get_brawler_range(self.current_brawler)
        decision=choose(self.current_brawler,self.brawlers_info[self.current_brawler],self.work_mode,player,self.context['enemy_data'],attack_range,super_range,
            lambda box:self.is_enemy_hittable(player,self.get_entity_pos(box),self.context['walls'],'super'))
        return self.use_super() if decision else False

    def configure_work_mode(self, level):
        from work_modes import style
        if level == self.work_mode and self._work_style is not None:
            return
        selected = style(level)
        if selected != self._work_style:
            from utils import load_playstyle_script
            info, source = load_playstyle_script(selected)
            self.playstyle_code = compile(source,'<work-mode>','exec')
            self._work_style = selected
        self.window_controller.release_all_inputs()
        self.behavior.reset()
        from bush_cover import BushCover
        self.bush_cover = BushCover()
        from incoming_damage import IncomingDamage
        self.incoming_damage = IncomingDamage()
        self.behavior_report = {}
        self.persistent_data['time_since_holding_attack'] = None
        self.work_mode = level

    def publish_debug_view(self, frame, data, state, movement=None):
        if not hasattr(self.window_controller, "debug_view"):
            return

        self.frame = frame
        advanced_visuals = bool(getattr(self.window_controller.debug_view, "advanced_visuals", False))
        debug_data = {
            "state": state,
            "player": [],
            "enemy": [],
            "teammate": [],
            "wall": [],
            "attack_range": 0,
            "super_range": 0,
            "poison_gas": {},
            "movement": None,
            "joystick": [self.window_controller.movement_joystick_x, self.window_controller.movement_joystick_y],
            "advanced_visuals": advanced_visuals,
            "joystick_radius": int(JOYSTICK_RADIUS * (self.window_controller.scale_factor or 1)),
            "joystick_directions": [],
            "enemy_los_lines": [],
            "teammate_los_lines": [],
            "player_hit_circle": None,
        }

        if data:
            for key in ["player", "enemy", "teammate", "wall"]:
                debug_data[key] = [[int(v) for v in box[:4]] for box in (data.get(key) or []) if len(box) >= 4]
            try:
                _, attack_range, super_range = self.get_brawler_range(self.current_brawler)
                debug_data["attack_range"] = int(attack_range)
                debug_data["super_range"] = int(super_range)
            except Exception:
                pass
            if debug_data["player"]:
                try:
                    debug_data["poison_gas"] = self.is_there_poison_gas(debug_data["player"][0])
                except Exception:
                    pass

        if movement is not None:
            debug_data["movement"] = [float(movement[0]), float(movement[1])]

        self.window_controller.debug_view.publish(frame, debug_data)

    def configure_thinking(self, level):
        """Keep the current per-device control while using classic navigation."""
        from thinking_levels import PROFILES
        if level == getattr(self, 'thinking_level', None):
            return
        profile = PROFILES[level]
        if not hasattr(self, '_thinking_base_intervals'):
            self._thinking_base_intervals = (self.walls_treshold, self.gas_detect_interval)
        self.thinking_level = level
        self.walls_treshold = (self._thinking_base_intervals[0] if profile['walls_interval'] is None
                               else profile['walls_interval'])
        self.gas_detect_interval = (self._thinking_base_intervals[1] if profile['gas_interval'] is None
                                    else profile['gas_interval'])
        self.time_since_walls_checked = 0.0
        self.gas_mask_time = 0.0

    def main(self, frame, brawler, main):
        quality = getattr(main, 'thinking', None)
        if quality is not None:
            self.configure_thinking(quality.mode)
        current_time = time.time()
        frame_time = getattr(main, 'current_frame_time', current_time)
        if not self.window_controller.frame_is_fresh(frame_time):
            self.window_controller.release_all_inputs()
            return
        state = main.get_latest_state()
        if state != 'match':
            self.window_controller.gameplay_frame_time = None
            self.window_controller.release_all_inputs()
            self.clear_gas_state()
            self.world_state = {'timestamp': frame_time, 'player_present': False, 'state': state}
            return
        from battle_perception import respawning
        from state_finder import is_respawning
        if respawning(frame) or is_respawning(frame):
            self.window_controller.release_all_inputs()
            self.window_controller.gameplay_frame_time = None
            self.clear_gas_state()
            self.reset_battle_pending = True
            self.context = None
            self.persistent_data['time_since_holding_attack'] = None
            self.world_state = {'timestamp':frame_time,'state':'respawning','player_present':False}
            return
        if self.reset_battle_pending:
            self.behavior.reset()
            from bush_cover import BushCover
            self.bush_cover = BushCover()
            from incoming_damage import IncomingDamage
            self.incoming_damage = IncomingDamage()
            self.behavior_report = {}
            self.battle_memory.reset()
            self.steering = Steering()
            self.ability_buttons = AbilityButtons()
            self.fix_movement_keys['toggled'] = False
            self.reset_battle_pending = False
        self.window_controller.gameplay_frame_time = frame_time
        self._thinking_battle_frame_time = frame_time
        data = self.get_main_data(frame)
        fresh_memory_walls = current_time - self.time_since_walls_checked > self.walls_treshold
        if fresh_memory_walls:
            tile_data = self.get_tile_data(frame, data.get("player"))
            walls, bushes = self.process_tile_data(tile_data)
            self.time_since_walls_checked = time.time()
            self.last_walls_data = walls
            data['wall'] = walls
            self.last_bushes_data = bushes
            data['bush'] = bushes
        else:
            data['wall'] = self.last_walls_data
            data['bush'] = self.last_bushes_data

        from battle_perception import own_player
        data = self.validate_game_data(own_player(data))
        self.track_no_detections(data)
        if data:
            self.time_since_player_last_found = time.time()

        if not data:
            # No player to measure, so the last gas reading would be about a
            # brawler that is no longer on screen.
            self.clear_gas_state()
            # Menus are handled by StageManager. Never guess a menu tap merely
            # because the player detector missed one battle frame.
            self.window_controller.release_all_inputs()
            self.world_state = {'timestamp': frame_time, 'player_present': False, 'state': state}
            self.publish_debug_view(frame, data, state)
            return
        self.time_since_last_proceeding = current_time
        self.battle_memory.update(data,current_time,self.TILE_SIZE*self.window_controller.scale_factor,fresh_memory_walls)
        self.ability_buttons.observe(frame,self.window_controller.press_coords_dict,current_time)
        for ability in ('super','gadget','hypercharge'):
            setattr(self,'is_'+ability+'_ready',self.ability_buttons.ready.get(ability) is not None)
        self.frame = frame
        # Gas is read before the playstyle runs, so the escape it hands over is
        # already known when the playstyle asks what to do.
        player_box = data['player'][0] if data.get('player') else None
        gas_movement = self.avoid_gas(frame, player_box, data.get('wall') or [], current_time)
        if self.gas_avoidance and not self.gas_detection_ok:
            self.gas_state = 'UNAVAILABLE'
            self.window_controller.release_all_inputs()
            self.world_state = {'timestamp': frame_time, 'state': 'match', 'player_present': True,
                                'gas_detection_ok': False, 'reason': 'gas_detector_unavailable'}
            return
        if not self.window_controller.begin_gameplay_frame(frame, frame_time):
            self.window_controller.release_all_inputs()
            return
        movement = self.loop(brawler, data, current_time, gas_movement)
        self.gas_state = 'ESCAPE' if self.gas_in_danger else 'SAFE'
        self.latency.update(entity_ms=self.Detect_main_info.last_inference_ms,
                            gas_ms=getattr(self.Detect_gas, 'last_inference_ms', 0.0),
                            wall_ms=(self.Detect_centered_tile_detector or self.Detect_tile_detector).last_inference_ms)
        self.world_state = {'timestamp': frame_time, 'detected_time': time.time(),
                            'frame_size': list(frame.shape[:2]), 'player_present': True,
                            'state': 'match', 'brawler': brawler, 'mode_confirmed': True,
                            'work_mode': self.work_mode, 'behavior': dict(self.behavior_report),
                            'visible_teammates': len(data['teammate']),
                            'idle_teammates': self.battle_memory.idle_count,
                            'remembered_dangers': len(self.battle_memory.dangers),
                            'remembered_paths': len(self.battle_memory.paths),
                            'player': data['player'], 'enemy': data['enemy'],
                            'teammate': data['teammate'], 'wall': data['wall'], 'bush': data['bush'],
                            'gas_boxes': self.gas_boxes, 'gas_coverage': self.gas_coverage,
                            'gas_detections': getattr(self.Detect_gas, 'last_detections', []),
                            'gas_model_confidence_threshold': self.gas_confidence,
                            'gas_observed_at': self.gas_observed_at,
                            'movement': self.safety_telemetry, 'abilities': self.ability_buttons.snapshot()}
        self.publish_debug_view(frame, data, state, movement)
        if movement is not None:
            started = time.perf_counter()
            self.do_movement(movement)
            self.latency['input_ms'] = (time.perf_counter()-started)*1000
