"""
Running and replaying an experiment
===================================

Active Learning experiments can be long and costly. For this reason,
it is useful to be able to resume an experiment if an error happened.
Cardinal also allows to compute the values of a metric after an
experiment has been run thanks to its ReplayCache.
"""

##############################################################################
# Those are the necessary imports and initializations

import shutil
import os
import numpy as np
import dataset

from sklearn.datasets import load_iris
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split

from cardinal.random import RandomSampler
from cardinal.uncertainty import MarginSampler
from cardinal.cache import ReplayCache
from cardinal.utils import GrowingIndex

##############################################################################
# Since we will be looking at the cache, we need a utility function to display
# a tree folder.

def list_files(startpath):
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print('{}{}/'.format(indent, os.path.basename(root)))
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print('{}{}'.format(subindent, f))

#############################################################################
# We load the data and define the parameters of this experiment:  
#
# * ``batch_size`` is the number of samples that will be annotated and added to
#   the training set at each iteration,
# * ``n_iter`` is the number of iterations in our simulation

iris = load_iris()
X = iris.data
y = iris.target

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.5, random_state=1)
batch_size = 5
n_iter = 10

model = SVC(probability=True)

samplers = [
    ('margin', MarginSampler(model, batch_size))
]

#############################################################################
# This function runs an experiment and optionally generate an error to test
# the resuming capability.
#
# Note the use of the GrowingIndex utils that facilitate the handing of
# indices in an active learning experiment.

def test_run(with_error=False, compute_metric=None):

    for sampler_name, sampler in samplers:

        config = dict(sampler=sampler_name)

        with ReplayCache('./cache', './cache.db', keys=config) as cache:

            index = GrowingIndex(X_train.shape[0])

            # Add at least one sample from each class
            index.add_to_selected([np.where(y_train == i)[0][0] for i in np.unique(y)])

            selected = cache.variable('selected', index.selected)

            for j, prev_selected in cache.iter(range(n_iter), selected.previous()):
                print('Computing iteration {}'.format(j))
                index.resume(prev_selected)

                model.fit(X_train[prev_selected], y_train[prev_selected])
                sampler.fit(X_train[prev_selected], y_train[prev_selected])
                index.add_to_selected(sampler.select_samples(X_train[index.non_selected]))
                selected.set(index.selected)

                if with_error and j == 5:
                    raise ValueError('Simulated Error')

            if compute_metric is not None:
                cache.compute_metric('metric', compute_metric, selected.previous(), selected.current())


#############################################################################
# We run this function and force an error to happen. We then see how the
# cache stores these values in a human readable way.
#
# We see that all selected indices have been kept up until the 4th iteration
# (since an error happened at iteration 5).

try:
    test_run(with_error=True)
except ValueError as e:
    print('ValueError raised: ' + str(e))
list_files('./cache')

#############################################################################
# We run the same function without error. In this case, we see that the 4
# first iterations are skipped. The code is not even executed. Afterward,
# the cache contains the data for all iterations.

test_run()
list_files('./cache')

#############################################################################
# Being a bit paranoid, we would like to check what cardinal does. For that,
# we compute the batch size of each iteration. Fortunately, we have cached
# the variable `selected` and therefore, we can replay the experiment.


def calc_batch_size(previous, current):
    return current.sum() - previous.sum()


test_run(compute_metric=calc_batch_size)

for r in dataset.connect('sqlite:///cache.db')['metric'].all():
    if r['id'] == 1:
        print('\t'.join(r.keys()))
    print('\t'.join(map(str, r.values())))


#############################################################################
# We clean all the cache folder.

shutil.rmtree('./cache')
os.remove('./cache.db')