"""Five behavior policies independent of the Think perception budget."""
import math

NAMES = {1:'Осторожность',2:'Выживание',3:'Баланс',4:'Агрессия',5:'Натиск'}


def resolve(config):
    value=config.get('work_mode')
    if type(value) is int and value in NAMES:
        return value
    from built_in_playstyles import canonical_playstyle
    return 4 if canonical_playstyle(config.get('current_playstyle'))=='aggressive.xlambot' else 2


def style(level):
    return 'aggressive.xlambot' if level>=4 else 'survivor.xlambot'


def movement(level, base, player, enemies, allies, attack_range, safe_range, tile, radius):
    if not enemies:
        return base
    center=lambda b:((b[0]+b[2])/2,(b[1]+b[3])/2)
    distance=lambda p:math.hypot(p[0]-player[0],p[1]-player[1])
    target=min((center(b) for b in enemies),key=distance)
    length=distance(target)
    near=sum(distance(center(b))<tile*5 for b in enemies)
    support=sum(distance(center(b))<tile*5 for b in allies)
    sign=None
    if level==1 and length<max(attack_range*1.25,tile*7):
        sign=-1  # even a lone opponent is a reason to retreat
    elif level==3:
        if near>support+1 and length<tile*6:
            sign=-1
        elif near<=support+1 and length>max(tile,attack_range*.7):
            sign=1
    elif level==5 and length>max(tile*.8,attack_range*.18):
        sign=1  # deliberately closes distance instead of preserving safe range
    if sign is None or length<1e-6:
        return base
    return (sign*(target[0]-player[0])*radius/length,sign*(target[1]-player[1])*radius/length)


def danger_weight(level):
    return {1:1.8,2:1.,3:.75,4:.5,5:.2}[level]
