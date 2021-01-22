"""
=================================
05. Source reconstruction and HNN
=================================

This example demonstrates how to calculate the inverse solution of the median
nerve evoked response in the MNE somatosensory dataset, and then simulate a
matching inverse solution with HNN.
"""

# Authors: Mainak Jas <mainakjas@gmail.com>
#          Ryan Thorpe <ryan_thorpe@brown.edu>

# sphinx_gallery_thumbnail_number = 2

###############################################################################
# First, we will import the packages needed for computing the inverse solution
# from the MNE somatosensory dataset. `MNE`_ can be installed with
# ``pip install mne``, and the somatosensory dataset can be downloaded by
# importing ``somato`` from ``mne.datasets``.
import os.path as op
import numpy as np
import matplotlib.pyplot as plt

import mne
from mne.datasets import somato
from mne.minimum_norm import apply_inverse, make_inverse_operator

###############################################################################
# Now we set the the path for the 1st subject of the ``somato`` dataset.
data_path = somato.data_path()
subject = '01'
task = 'somato'
raw_fname = op.join(data_path, 'sub-{}'.format(subject), 'meg',
                    'sub-{}_task-{}_meg.fif'.format(subject, task))
fwd_fname = op.join(data_path, 'derivatives', 'sub-{}'.format(subject),
                    'sub-{}_task-{}-fwd.fif'.format(subject, task))
subjects_dir = op.join(data_path, 'derivatives', 'freesurfer', 'subjects')

###############################################################################
# Then, we get the raw data and estimate the inverse operator.

raw = mne.io.read_raw_fif(raw_fname, preload=True)
raw.filter(1, 40)

events = mne.find_events(raw, stim_channel='STI 014')
event_id, tmin, tmax = 1, -.2, .17
baseline = None
epochs = mne.Epochs(raw, events, event_id, tmin, tmax, baseline=baseline,
                    reject=dict(grad=4000e-13, eog=350e-6), preload=True)
evoked = epochs.average()

fwd = mne.read_forward_solution(fwd_fname)
cov = mne.compute_covariance(epochs)
inv = make_inverse_operator(epochs.info, fwd, cov)

###############################################################################
# There are several methods to do source reconstruction. Some of the methods
# such as MNE are distributed source methods whereas dipole fitting will
# estimate the location and amplitude of a single current dipole. At the
# moment, we do not offer explicit recommendations on which source
# reconstruction technique is best for HNN. However, we do want our users
# to note that the dipole currents simulate with HNN are assumed to be normal
# to the cortical surface. Hence, using the option ``pick_ori='normal'``
# seems to make most sense.

method = "MNE"
snr = 3.
lambda2 = 1. / snr ** 2
stc = apply_inverse(evoked, inv, lambda2, method=method, pick_ori="normal",
                    return_residual=False, verbose=True)

###############################################################################
# We isolate the single most active vertex in the distributed minimum norm
# estimate by calculating the L2 norm of the time course emerging from each
# vertex. The time course from the vertex with the greatest L2 norm represents
# the location of cortex with greatest response to stimulus.
pick_vertex = np.argmax(np.linalg.norm(stc.data, axis=1))

plt.figure()
plt.plot(1e3 * stc.times, stc.data[pick_vertex, :].T * 1e9, 'ro-')
plt.xlabel('time (ms)')
plt.ylabel('%s value (nAM)' % method)
plt.xlim((0, 170))
plt.axhline(0)
plt.show()

###############################################################################
# Now, let us try to simulate the same with hnn-core. We read in the network
# parameters from ``N20.json`` and explicitly create two distal and one
# proximal evoked drive.

import hnn_core
from hnn_core import simulate_dipole, read_params, Network, MPIBackend, average_dipoles

hnn_core_root = op.dirname(hnn_core.__file__)

params_fname = op.join(hnn_core_root, 'param', 'N20.json')
params = read_params(params_fname)

net = Network(params)

# Distal evoked drives share connection parameters
weights_ampa_d = {'L2_basket': 0.003, 'L2_pyramidal': 0.0045,
                  'L5_pyramidal': 0.001}
weights_nmda_d = {'L2_basket': 0.003, 'L2_pyramidal': 0.0045,
                  'L5_pyramidal': 0.001}
synaptic_delays_d = {'L2_basket': 0.1, 'L2_pyramidal': 0.1,
                     'L5_pyramidal': 0.1}
# early distal input
net.add_evoked_drive(
    'evdist1', mu=32., sigma=3., numspikes=1, sync_within_trial=True,
    weights_ampa=weights_ampa_d, weights_nmda=weights_nmda_d,
    location='distal', synaptic_delays=synaptic_delays_d, seedcore=6)
# late distal input
net.add_evoked_drive(
    'evdist2', mu=82., sigma=3., numspikes=1, sync_within_trial=True,
    weights_ampa=weights_ampa_d, weights_nmda=weights_nmda_d,
    location='distal', synaptic_delays=synaptic_delays_d, seedcore=2)

# proximal input occurs before distals
weights_ampa_p = {'L2_basket': 0.003, 'L2_pyramidal': 0.0025,
                  'L5_basket': 0.004, 'L5_pyramidal': 0.001}
weights_nmda_p = {'L2_basket': 0.003, 'L5_basket': 0.004}
synaptic_delays_p = {'L2_basket': 0.1, 'L2_pyramidal': 0.1,
                     'L5_basket': 1.0, 'L5_pyramidal': 1.0}
net.add_evoked_drive(
    'evprox1', mu=20.0, sigma=3., numspikes=1, sync_within_trial=True,
    weights_ampa=weights_ampa_p, weights_nmda=weights_nmda_p,
    location='proximal', synaptic_delays=synaptic_delays_p, seedcore=6)

# n_trials = 25
n_trials = 1
with MPIBackend(n_procs=6, mpi_cmd='mpiexec'):
    dpls = simulate_dipole(net, n_trials=25)

fig, axes = plt.subplots(3, 1, sharex=True, figsize=(6, 6))
axes[1].plot(1e3 * stc.times, stc.data[pick_vertex, :].T * 1e9, 'r-')
net.cell_response.plot_spikes_hist(ax=axes[0], show=False)
average_dipoles(dpls).plot(ax=axes[1], show=False)
net.cell_response.plot_spikes_raster(ax=axes[2])

###############################################################################
# .. LINKS
#
# .. _MNE: https://mne.tools/
