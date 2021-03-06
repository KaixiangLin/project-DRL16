#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: varmanip.py
# Author: Yuxin Wu <ppwwyyxxc@gmail.com>

import six
import tensorflow as tf
from collections import defaultdict
import re
import numpy as np
from ..utils import logger
from ..utils.naming import *
from .common import get_op_tensor_name

__all__ = ['SessionUpdate', 'dump_session_params', 'dump_chkpt_vars',
        'get_savename_from_varname', 'is_training_name']

def get_savename_from_varname(
        varname, varname_prefix=None,
        savename_prefix=None):
    """
    :param varname: a variable name in the graph
    :param varname_prefix: an optional prefix that may need to be removed in varname
    :param savename_prefix: an optional prefix to append to all savename
    :returns: the name used to save the variable
    """
    name = varname
    if 'towerp/' in name:
        logger.error("No variable should be under 'towerp' name scope".format(v.name))
        # don't overwrite anything in the current prediction graph
        return None
    if 'tower' in name:
        name = re.sub('tower[p0-9]+/', '', name)
    if varname_prefix is not None \
            and name.startswith(varname_prefix):
        name = name[len(varname_prefix)+1:]
    if savename_prefix is not None:
        name = savename_prefix + '/' + name
    return name

class SessionUpdate(object):
    """ Update the variables in a session """
    def __init__(self, sess, vars_to_update):
        """
        :param vars_to_update: a collection of variables to update
        """
        self.sess = sess
        self.assign_ops = defaultdict(list)
        for v in vars_to_update:
            #p = tf.placeholder(v.dtype, shape=v.get_shape())
            with tf.device('/cpu:0'):
                p = tf.placeholder(v.dtype)
                savename = get_savename_from_varname(v.name)
                # multiple vars might share one savename
                self.assign_ops[savename].append((p, v, v.assign(p)))

    def update(self, prms):
        """
        :param prms: dict of {variable name: value}
        Any name in prms must be in the graph and in vars_to_update.
        """
        for name, value in six.iteritems(prms):
            assert name in self.assign_ops
            for p, v, op in self.assign_ops[name]:
                varshape = tuple(v.get_shape().as_list())
                if varshape != value.shape:
                    # TODO only allow reshape when shape different by empty axis
                    assert np.prod(varshape) == np.prod(value.shape), \
                            "{}: {}!={}".format(name, varshape, value.shape)
                    logger.warn("Param {} is reshaped during assigning".format(name))
                    value = value.reshape(varshape)
                self.sess.run(op, feed_dict={p: value})

def dump_session_params(path):
    """ Dump value of all trainable + to_save variables to a dict and save to `path` as
    npy format, loadable by ParamRestore
    """
    var = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES)
    var.extend(tf.get_collection(EXTRA_SAVE_VARS_KEY))
    result = {}
    for v in var:
        name = get_savename_from_varname(v.name)
        if name in result:
            logger.info("Variable {} would be stored instead of another with \
the same name".format(v.name))
        result[name] = v.eval()
    logger.info("Variables to save to {}:".format(path))
    logger.info(str(result.keys()))
    np.save(path, result)

def dump_chkpt_vars(model_path):
    """ Dump all variables from a checkpoint to a dict"""
    reader = tf.train.NewCheckpointReader(model_path)
    var_names = reader.get_variable_to_shape_map().keys()
    result = {}
    for n in var_names:
        result[n] = reader.get_tensor(n)
    return result

def is_training_name(name):
    """
    This is only used to improve logging.
    :returns: guess whether this tensor is something only used in training.
    """
    # TODO: maybe simply check against TRAINABLE_VARIABLES and EXTRA_SAVE_VARS_KEY ?
    # TODO or use get_slot_names()
    name = get_op_tensor_name(name)[0]
    if name.endswith('/Adam') or name.endswith('/Adam_1'):
        return True
    if name.endswith('/Momentum'):
        return True
    if name.endswith('/Adadelta') or name.endswith('/Adadelta_1'):
        return True
    if name.endswith('/RMSProp') or name.endswith('/RMSProp_1'):
        return True
    if name.endswith('/Adagrad'):
        return True
    if 'EMA_summary/' in name:
        return True
    return False
