import time
import threading
import argparse
import numpy as np
from p5 import *  # pip install p5

from policy import Policy
from policy_boids_vanilla import Policy_Boids_Vanilla
from policy_random_network import Policy_Random_Network
from policy_follow_leader import Policy_Follow_Leader

from metric import Metric, MicroEntropyMetric, MacroEntropyMetric

import utils
from world import World

Policy_classes = {
    "Policy": Policy,
    "Policy_Boids_Vanilla": Policy_Boids_Vanilla,
    "Policy_Random_Network": Policy_Random_Network,
    "Policy_Follow_Leader": Policy_Follow_Leader,
}

Metric_classes = {
    "Metric": Metric,
    "Micro_Entropy": MicroEntropyMetric,
    "Macro_Entropy": MacroEntropyMetric,
}

class Simulation(threading.Thread):
    def run(self):
        global g_obs, g_world, g_metrics, g_metrics_val
        g_world = World(seed=0)
        g_world.init_vehicles(args.num_vehicles)

        g_metrics = Metric_classes[args.metric_class](world=g_world)

        g_policy = Policy_classes[args.policy_class](world=g_world, dim_obs=g_world.dim_obs, dim_action=g_world.dim_action)

        obs = g_world.reset()

        while True:
            action = g_policy.get_action(obs)
            obs, info = g_world.step(action)
            g_metrics_val[0] = g_metrics.get_metric()
            # set g_obs for visualization
            g_obs = g_world.get_absolute_obs()
            time.sleep(0.01)


# P5 interface

def setup():
    size(g_world.width, g_world.height)
    no_stroke()


def draw():
    # utils.reset_timer("Outside Draw Function")
    hack_check_window_size()
    background(27, 73, 98)
    draw_info()
    all_vehicles = g_obs
    for i, v in enumerate(all_vehicles):
        v = v[:3] # first three observations are pos_x, pos_y, angle
        draw_vehicle(*v, vehicle_id=i)
    # utils.reset_timer("In Draw Function")


def draw_info():
    global g_last_step
    step_per_frame = g_world.time_step - g_last_step
    g_last_step = g_world.time_step
    with push_matrix():
        translate(10, 10)
        text(f"Time Step: {g_world.time_step}", 0, 0)
        text(f"{args.metric_class}: {g_metrics_val[0]:.03f}", 0, 15)
        text(f"Step per frame: {step_per_frame}", 0, 30)


def hack_check_window_size():
    """ I use tile in Linux, so window size changes after it opens. """
    global g_world
    if g_world.width != p5.sketch.size[0] and g_world.height != p5.sketch.size[1]:
        g_world.width = p5.sketch.size[0]
        g_world.height = p5.sketch.size[1]


def draw_vehicle(pos_x, pos_y, angle, vehicle_id):
    p1 = [0, 10]
    p2 = [-3, -5]
    p3 = [+3, -5]
    # p4 = [-1, +5]
    # p5 = [+1, +5]
    with push_matrix():
        with push_style():
            translate(pos_x * g_world.width, pos_y * g_world.height)
            with push_matrix():
                rotate(-angle)
                scale(1.3)
                fill(Color(136, 177, 112))
                triangle(p1, p2, p3)
                # less decoration, a little faster.
                # fill(Color(162, 184, 167))
                # triangle(p1, p4, p5)
            text(f"{vehicle_id}", 0, -20)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--num-vehicles", type=int, default=10, help="Number of vehicles")
    parser.add_argument("-p", "--policy-class", type=str, default="Policy", help="The name of the policy class you want to use.")
    parser.add_argument("-m", "--metric-class", type=str, default="Metric", help="The name of the metric class you want to use.")
    args = parser.parse_args()
    g_obs = None
    g_world = None
    g_metrics = None
    g_metrics_val = [0.]
    g_last_step = 0
    print("Press Ctrl+C twice to quit...")
    # Start Simulation Thread
    sim = Simulation()
    sim.start()
    # Start to draw using p5
    run()
