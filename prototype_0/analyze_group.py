from dask import delayed
from dask.distributed import Client, LocalCluster
from dask_jobqueue import SLURMCluster
import glob
import pickle
import numpy as np
import scipy.stats
import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
from metric_hse import HSEMetric

cluster = SLURMCluster(memory='2g',
                    cores=1,
                    queue='short',
                    walltime="03:00:00",
                    job_extra=['--job-name="simworker"', "--output=/users/d/m/dmatthe1/job_logs/dask-%x-%A.txt"])

cluster.scale(30)
client = Client(cluster)


def investigate(x, y):
    """x and y are observations of X and Y"""
    assert x.shape == y.shape, "Can't do mutual information on observations of different length"

    xy = np.c_[x, y]  # a faster way of doing xy = zip(x,y) and turn to array

    vals_x, counts_x = np.unique(x, return_counts=True, axis=0)
    vals_y, counts_y = np.unique(y, return_counts=True, axis=0)
    vals_xy, counts_xy = np.unique(xy, return_counts=True, axis=0)

    # H(X)
    Hx = scipy.stats.entropy(counts_x, base=2)
    # H(Y)
    Hy = scipy.stats.entropy(counts_y, base=2)
    # H(X,Y)
    Hxy = scipy.stats.entropy(counts_xy, base=2)
    # H(Y|X)
    Hy_given_x = Hxy - Hx
    # H(X|Y)
    Hx_given_y = Hxy - Hy
    # I(X;Y)
    MI_xy = Hy - Hy_given_x

    return (Hx, Hy, Hxy, Hy_given_x, Hx_given_y, MI_xy, MI_xy/min(Hx, Hy))


def process_data_HSE(fname):
    seed_id = int(fname[fname.find("steps_")+6:-6])

    # read from disk
    data = pickle.load(open(fname, "rb"))
    
    # reshape to (time, vid, states)
    data = data.reshape((data.shape[0], -1, 4))
    n_steps_full = data.shape[0]
    
    n_steps = 100
    step_size = n_steps_full//n_steps
    entropies = np.zeros(shape=(n_steps, 3))
    entropies[:, 0] = seed_id
    h = HSEMetric(None)
    row_idx = 0
    for row_idx in range(n_steps):
        entropies[row_idx, 1] = row_idx*step_size
        entropies[row_idx, 2] = h.get_metric_no_world(data[row_idx*step_size, :, :2])["HSE"]
    return  entropies


def process_data_MI(fname, nbins):
    # read from disk
    data = pickle.load(open(fname, "rb"))
    
    # reshape to (time, vid, states)
    data = data.reshape((data.shape[0], -1, 4))
    
    # bin to nbins
    binned_data = (data * nbins).astype(np.int)

    velocity_binned_data = binned_data[:,:,2]
    n_vehicles = velocity_binned_data.shape[1]

    all_entropies = np.zeros(shape=((n_vehicles*(n_vehicles-1))//2, 10))
    row_id = 0
    seed_id = int(fname[fname.find("steps_")+6:-6])
    for v_id_a in range(n_vehicles):
        x_series = velocity_binned_data[:, v_id_a]
        for v_id_b in range(v_id_a+1, n_vehicles):
            y_series = velocity_binned_data[:, v_id_b]
            row_dat = investigate(x_series, y_series)
            all_entropies[row_id, 3:] = row_dat
            all_entropies[row_id, :3] = (seed_id, v_id_a, v_id_b)
            row_id += 1

    return all_entropies, np.mean(all_entropies, axis=0)

def main(client, fnames, nbins):
    results_MI = []
    results_HSE = []
    for fname in fnames:
        results_MI.append(delayed(process_data_MI)(fname, nbins))

    for fname in fnames:
        results_HSE.append(delayed(process_data_HSE)(fname))
    
    merged_data_MI = []
    for fut in client.compute(results_MI):
        res = fut.result()
        merged_data_MI.append(res)

    merged_data_HSE = []
    for fut in client.compute(results_HSE):
        res = fut.result()
        merged_data_HSE.append(res)

    return merged_data_MI, merged_data_HSE


policies = ["Policy", "Policy_Random", "Policy_Random_Network", "Policy_Random_Network2", "Policy_Follow_Leader", "Policy_Boids", "Policy_Simplified_Boids"]

dfsMI = []
dfsHSE = []
for policy in policies:
    fnames = glob.glob("data/{}_10agents_10000steps*".format(policy))

    dat_MI, dat_HSE = main(client, fnames, 10)

    stacked_entropies_MI = np.vstack([d[0] for d in dat_MI])
    stacked_entropies_HSE = np.vstack( dat_HSE)

    dfMI = pd.DataFrame(stacked_entropies_MI, columns=["Seed", "Vehicle_A", "Vehicle_B", "Hx", "Hy", "Hxy", "Hy_given_x", "Hx_given_y", "MI_xy", "MI_xy_Normalized"])
    dfHSE = pd.DataFrame(stacked_entropies_HSE, columns=["Seed", "Time", "HSE"])
    dfMI.insert(0, "Policy", policy)
    dfHSE.insert(0, "Policy", policy)
    dfsMI.append(dfMI)
    dfsHSE.append(dfHSE)

dfMI = pd.concat(dfsMI)
dfHSE = pd.concat(dfsHSE)

ldf = pd.wide_to_long(dfMI, stubnames=[""], i=["Policy", "Seed", "Vehicle_A", "Vehicle_B"], j="Metric", sep="", suffix='[HM]\w+')
ldf.reset_index(inplace=True)
ldf.rename(columns={"":"Value"}, inplace=True)

ldfsub = ldf[ldf["Metric"] == "MI_xy_Normalized"]

fig, ax = plt.subplots(figsize=(6,4))
sns.barplot(y="Policy", x="Value", hue="Metric",ci=95, data=ldfsub, ax=ax)
plt.savefig("Normalized_MI_Entropies.pdf", bbox_inches='tight')
plt.show()

fig, ax = plt.subplots(figsize=(4*7,4))
sns.barplot(x="Policy", y="Value", hue="Metric",ci=95, data=ldf, ax=ax)
plt.savefig("MI_Entropies.pdf")
plt.show()


fig, ax = plt.subplots(figsize=(6,4))
sns.barplot(y="Policy", x="HSE", ci=95, data=dfHSE, ax=ax)
plt.savefig("HSE_Entropies.pdf")
plt.show()

dfHSETMP = dfHSE[dfHSE["Seed"] == 1]
fig, ax = plt.subplots(figsize=(6,4))
sns.lineplot(x="Time", y="HSE", hue="Policy", data=
                            dfHSETMP,
                             ax=ax, ci="sd")
box = ax.get_position()
ax.set_position([box.x0, box.y0 + box.height * 0.1,
                 box.width, box.height * 0.9])

# Put a legend below current axis
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15),
           ncol=2)
plt.savefig("HSE_Entropies_Over_Time_Seed_1.pdf", bbox_inches='tight')
plt.show()

dfHSETMP = dfHSE[dfHSE["Seed"] == 2]
fig, ax = plt.subplots(figsize=(6,4))
sns.lineplot(x="Time", y="HSE", hue="Policy", data=
                            dfHSETMP,
                             ax=ax, ci="sd")
box = ax.get_position()
ax.set_position([box.x0, box.y0 + box.height * 0.1,
                 box.width, box.height * 0.9])

# Put a legend below current axis
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15),
           ncol=2)
plt.savefig("HSE_Entropies_Over_Time_Seed_2.pdf",bbox_inches='tight')
plt.show()

dfHSETMP = dfHSE[dfHSE["Seed"]==1]
min_row = dfHSETMP.values[dfHSETMP["HSE"].argmin()]
data = pickle.load(open("data/{}_10agents_10000steps_1seed.p".format(min_row[0]), "rb"))
data = data.reshape((data.shape[0], -1, 4))
min_row_pos = data[int(min_row[2]), :, :2]
plt.scatter(min_row_pos[:, 0], min_row_pos[:, 1], label="HSE: {:.2f}".format(min_row[-1]))

max_row = dfHSETMP.values[dfHSETMP["HSE"].argmax()]
data = pickle.load(open("data/{}_10agents_10000steps_1seed.p".format(max_row[0]), "rb"))
data = data.reshape((data.shape[0], -1, 4))
max_row_pos = data[int(max_row[2]), :, :2]

plt.scatter(max_row_pos[:, 0], max_row_pos[:, 1], label="HSE: {:.2f}".format(max_row[-1]))

plt.xlim((0,1))
plt.ylim((0,1))
plt.legend()
plt.savefig("HSE_Entropies_Min_Max_Seed_1.pdf",bbox_inches='tight')
