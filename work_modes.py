"""Five behavior policies independent of the Think perception budget."""

NAMES = {1:'Сидеть в кустах',2:'Выживание',3:'Баланс',4:'Агрессия',5:'Натиск'}


def resolve(config):
    value=config.get('work_mode')
    if type(value) is int and value in NAMES:
        return value
    from built_in_playstyles import canonical_playstyle
    return 4 if canonical_playstyle(config.get('current_playstyle'))=='aggressive.xlambot' else 2


def style(level):
    return 'aggressive.xlambot' if level>=4 else 'survivor.xlambot'


def movement(level, base, player, enemies, allies, attack_range, safe_range, tile, radius):
    from combat_behavior import CombatBehavior
    plan=CombatBehavior().plan(level,player,enemies,allies,attack_range,safe_range,tile,radius,0.)
    return base if plan['movement'] is None else plan['movement']


def danger_weight(level):
    return {1:1.8,2:1.,3:.75,4:.5,5:.2}[level]
