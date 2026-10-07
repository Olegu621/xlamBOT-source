"""Ability-specific range/visibility, independent of normal attack line of sight."""
import math

def choose(brawler,info,mode,player,enemies,attack_range,super_range,visible):
    kind=info.get('super_type','damage')
    for box in enemies:
        point=((box[0]+box[2])/2,(box[1]+box[3])/2);distance=math.dist(player,point)
        if mode==1 and distance>attack_range*.65:continue
        if kind=='spawnable':
            if distance<=attack_range*1.25:return True
        elif kind=='other':
            if distance<=max(attack_range,super_range):return True
        elif visible(box) and distance<=super_range+(attack_range if brawler in ('stu','surge') and kind=='charge' else 0):return True
    return False
