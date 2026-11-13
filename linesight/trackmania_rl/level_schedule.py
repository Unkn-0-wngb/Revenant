"""
Decides which level is being trained, and which runs a collector should do next.
A level is only left once it has been finished min_finishes_per_level times this visit and has had its step budget
(smaller once the goal time, author, is beaten). Without the goal it also stays while it keeps setting faster times.
max_steps_per_level stops a level that can't be finished from holding up the loop forever.
focus_level jumps to one level and stays there until focus_target_s is beaten (or focus_level is cleared), then goes
back to the level it left.
"""

import json


def starting_level(save_dir, levels):
    path = save_dir / "cycle_position.json"
    if not path.exists():
        return 0
    level = json.loads(path.read_text(encoding="utf-8"))["level"]
    names = [entry[0] for entry in levels]
    return names.index(level) if level in names else 0


def step_budget(short_name, stats, config):
    best = stats["alltime_min_ms"].get(short_name)
    if best is not None and best / 1000 <= config.goal_times[short_name]:
        return config.steps_per_level_with_gold
    return config.steps_per_level


def focus_index(stats, config):
    focus = getattr(config, "focus_level", "")
    names = [entry[0] for entry in config.levels]
    if focus not in names:
        return None
    best = stats["alltime_min_ms"].get(focus)
    if best is not None and best / 1000 <= config.focus_target_s:
        return None
    return names.index(focus)


def next_level_index(stats, config):
    index = stats["level_index"] % len(config.levels)
    focus = focus_index(stats, config)
    names = [entry[0] for entry in config.levels]
    if focus is not None:
        if index != focus:
            stats.setdefault("return_level", names[index])
            return focus
        return None
    if "return_level" in stats:
        level = stats.pop("return_level")
        stats.pop("return_index", None)
        if level in names and names.index(level) != index:
            return names.index(level)
        return None
    if "return_index" in stats:
        return stats.pop("return_index") % len(names)
    short_name = config.levels[index][0]
    frames = stats["cumul_number_frames_played"]
    used = frames - stats["level_start_frames"]
    move_on = (index + 1) % len(config.levels)
    if used >= config.max_steps_per_level:
        return move_on
    if stats.get("level_finishes", 0) < config.min_finishes_per_level:
        return None
    if used < step_budget(short_name, stats, config):
        return None
    best = stats["alltime_min_ms"].get(short_name)
    if best is not None and best / 1000 <= config.goal_times[short_name]:
        return move_on
    since_best = frames - stats.get("level_best_frames", stats["level_start_frames"])
    if since_best >= config.steps_without_improvement:
        return move_on
    return None


def next_run(level_index, loop_number, checkups_done, process_number, levels, checkup_every_n_runs):
    """
    Returns (map tuple, is this a check-up). A check-up is a test lap on an older level that isn't trained on.
    Only the first game does them, so only one window changes level at a time.
    """
    if checkup_every_n_runs and process_number == 0 and level_index > 0 and loop_number % checkup_every_n_runs == 0:
        short_name, path, line = levels[checkups_done % level_index]
        return (short_name, path, line, False, False), True
    short_name, path, line = levels[level_index]
    return (short_name, path, line, loop_number % 5 != 0, True), False
