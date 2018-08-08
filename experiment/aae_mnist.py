#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: aae_mnist.py
# Author: Qian Ge <geqian1001@gmail.com>

import os
import sys
import numpy as np
import tensorflow as tf
import platform
import scipy.misc
import argparse
# import matplotlib.pyplot as plt

sys.path.append('../')
from src.dataflow.mnist import MNISTData
from src.models.aae import AAE
from src.helper.trainer import Trainer
from src.helper.generator import Generator
from src.helper.visualizer import Visualizer
import src.models.distribution as distribution

if platform.node() == 'Qians-MacBook-Pro.local':
    DATA_PATH = '/Users/gq/workspace/Dataset/MNIST_data/'
    SAVE_PATH = '/Users/gq/tmp/vae/style/'
    RESULT_PATH = '/Users/gq/tmp/ram/center/result/'
elif platform.node() == 'arostitan':
    DATA_PATH = '/home/qge2/workspace/data/MNIST_data/'
    SAVE_PATH = '/home/qge2/workspace/data/out/vae/'
else:
    DATA_PATH = 'E://Dataset//MNIST//'
    SAVE_PATH = 'E:/tmp/vae/tmp/'
    # RESULT_PATH = 'E:/tmp/ram/trans/result/'


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', action='store_true',
                        help='Train the model')
    parser.add_argument('--train_supervised', action='store_true',
                        help='Train the model')
    parser.add_argument('--train_semisupervised', action='store_true',
                        help='Train the model')
    
    parser.add_argument('--generate', action='store_true',
                        help='generate')
    parser.add_argument('--viz', action='store_true',
                        help='visualize')
    parser.add_argument('--style', action='store_true',
                        help='sample styles')
    parser.add_argument('--test', action='store_true',
                        help='test')
    parser.add_argument('--label', action='store_true',
                        help='use label for training')
    parser.add_argument('--noise', action='store_true',
                        help='add noise to input')
    parser.add_argument('--semi', action='store_true',
                        help='semi-supervise')
    parser.add_argument('--supervise', action='store_true',
                        help='supervise')
    parser.add_argument('--load', type=int, default=99,
                        help='Load step of pre-trained')
    parser.add_argument('--lr', type=float, default=2e-4,
                        help='Init learning rate')
    parser.add_argument('--dropout', type=float, default=1.0,
                        help='autoencoder dropout')
    parser.add_argument('--ncode', type=int, default=2,
                        help='number of code')

    parser.add_argument('--bsize', type=int, default=128,
                        help='Init learning rate')
    parser.add_argument('--maxepoch', type=int, default=100,
                        help='Max iteration')

    parser.add_argument('--encw', type=float, default=1.,
                        help='weight of encoder loss')
    parser.add_argument('--genw', type=float, default=6.,
                        help='weight of generator loss')
    parser.add_argument('--disw', type=float, default=6.,
                        help='weight of discriminator loss')

    parser.add_argument('--clsw', type=float, default=1.,
                        help='weight of semisupervised loss')
    parser.add_argument('--ygenw', type=float, default=6.,
                        help='weight of y generator loss')
    parser.add_argument('--ydisw', type=float, default=6.,
                        help='weight of y discriminator loss')

    parser.add_argument('--dist_type', type=str, default='gaussian',
                        help='prior')
    
    return parser.parse_args()


def preprocess_im(im):
    # im = im / 255.
    # im += np.random.normal(loc=0.0, scale=0.3, size=im.shape)
    # im = np.clip(im, 0, 1)
    # im = im * 2. - 1.

    im = im / 255. * 2. - 1.
    return im

def read_train_data(batch_size, n_use_label=None, n_use_sample=None):
    data = MNISTData('train',
                     data_dir=DATA_PATH,
                     shuffle=True,
                     pf=preprocess_im,
                     n_use_label=n_use_label,
                     n_use_sample=n_use_sample,
                     batch_dict_name=['im', 'label'])
    data.setup(epoch_val=0, batch_size=batch_size)
    return data

def read_valid_data(batch_size):
    data = MNISTData('test',
                     data_dir=DATA_PATH,
                     shuffle=True,
                     pf=preprocess_im,
                     batch_dict_name=['im', 'label'])
    data.setup(epoch_val=0, batch_size=batch_size)
    return data

def semisupervised_train():
    FLAGS = get_args()

    train_data_unlabel = read_train_data(FLAGS.bsize)
    train_data_label = read_train_data(FLAGS.bsize, n_use_sample=128)
    train_data = {'unlabeled': train_data_unlabel, 'labeled': train_data_label}
    valid_data = read_valid_data(FLAGS.bsize)

    train_model = AAE(n_code=FLAGS.ncode, wd=0, n_class=10, 
                use_label=False, use_supervise=False, add_noise=FLAGS.noise,
                enc_weight=FLAGS.encw, gen_weight=FLAGS.genw, dis_weight=FLAGS.disw,
                cat_dis_weight=FLAGS.ydisw, cat_gen_weight=FLAGS.ygenw, cls_weight=FLAGS.clsw)
    train_model.create_semisupervised_train_model()

    cls_valid_model = AAE(n_code=FLAGS.ncode, n_class=10)
    cls_valid_model.create_semisupervised_test_model()

    trainer = Trainer(train_model, cls_valid_model=cls_valid_model, generate_model=None,
                      train_data=train_data,
                      init_lr=FLAGS.lr, save_path=SAVE_PATH)

    sessconfig = tf.ConfigProto()
    sessconfig.gpu_options.allow_growth = True
    with tf.Session(config=sessconfig) as sess:
        writer = tf.summary.FileWriter(SAVE_PATH)
        sess.run(tf.global_variables_initializer())
        writer.add_graph(sess.graph)
        for epoch_id in range(FLAGS.maxepoch):
            trainer.train_semisupervised_epoch(sess, ae_dropout=FLAGS.dropout, summary_writer=writer)
            trainer.valid_semisupervised_epoch(sess, valid_data, summary_writer=writer)
    

def supervised_train():
    FLAGS = get_args()

    label_train_data = read_train_data(FLAGS.bsize, n_use_sample=1280)
    unlabel_train_data = read_train_data(FLAGS.bsize)
    valid_data = read_valid_data(FLAGS.bsize)

    model = AAE(n_code=FLAGS.ncode, wd=0, n_class=10, 
                use_label=False, use_supervise=True, add_noise=FLAGS.noise,
                enc_weight=FLAGS.encw, gen_weight=FLAGS.genw, dis_weight=FLAGS.disw)
    model.create_train_model()

    valid_model = AAE(n_code=FLAGS.ncode, use_supervise=True, n_class=10)
    valid_model.create_generate_model(b_size=400)
    valid_model.create_generate_style_model(n_sample=10)

    trainer = Trainer(model, valid_model, train_data, distr_type=FLAGS.dist_type, use_label=FLAGS.label,
                      init_lr=FLAGS.lr, save_path=SAVE_PATH)
    generator = Generator(generate_model=valid_model, save_path=SAVE_PATH,
                          distr_type=FLAGS.dist_type, n_labels=10, use_label=FLAGS.label)

    sessconfig = tf.ConfigProto()
    sessconfig.gpu_options.allow_growth = True
    with tf.Session(config=sessconfig) as sess:
        writer = tf.summary.FileWriter(SAVE_PATH)
        saver = tf.train.Saver()
        sess.run(tf.global_variables_initializer())
        writer.add_graph(sess.graph)

        for epoch_id in range(FLAGS.maxepoch):
            trainer.train_gan_epoch(sess, ae_dropout=FLAGS.dropout, summary_writer=writer)
            trainer.valid_epoch(sess, dataflow=valid_data, summary_writer=writer)
            
            if epoch_id % 10 == 0:
                saver.save(sess, '{}aae-epoch-{}'.format(SAVE_PATH, epoch_id))
                generator.sample_style(sess, valid_data, plot_size=10, file_id=epoch_id, n_sample=10)
        saver.save(sess, '{}aae-epoch-{}'.format(SAVE_PATH, epoch_id))

def train():
    FLAGS = get_args()
    plot_size = 20

    n_use_label=None
    if FLAGS.semi:
        n_use_label = 10000
        print('*** Only {} labels are used. ***'.format(n_use_label))

    train_data = read_train_data(FLAGS.bsize, n_use_label=n_use_label, n_use_sample=None)
    valid_data = read_valid_data(FLAGS.bsize)

    model = AAE(n_code=FLAGS.ncode, wd=0, n_class=10, 
                use_label=FLAGS.label, use_supervise=False, add_noise=FLAGS.noise,
                enc_weight=FLAGS.encw, gen_weight=FLAGS.genw, dis_weight=FLAGS.disw)
    model.create_train_model()

    valid_model = AAE(n_code=FLAGS.ncode, use_supervise=False, n_class=10)
    valid_model.create_generate_model(b_size=400)
    # if FLAGS.supervise:
    #     valid_model.create_generate_style_model(n_sample=10)

    trainer = Trainer(model, valid_model, train_data, distr_type=FLAGS.dist_type, use_label=FLAGS.label,
                      init_lr=FLAGS.lr, save_path=SAVE_PATH)
    # if FLAGS.ncode == 2:
    visualizer = Visualizer(model, save_path=SAVE_PATH)
    generator = Generator(generate_model=valid_model, save_path=SAVE_PATH,
                          distr_type=FLAGS.dist_type, n_labels=10, use_label=FLAGS.label)

    sessconfig = tf.ConfigProto()
    sessconfig.gpu_options.allow_growth = True
    with tf.Session(config=sessconfig) as sess:
        writer = tf.summary.FileWriter(SAVE_PATH)
        saver = tf.train.Saver()
        sess.run(tf.global_variables_initializer())
        writer.add_graph(sess.graph)

        for epoch_id in range(FLAGS.maxepoch):
            trainer.train_gan_epoch(sess, ae_dropout=FLAGS.dropout, summary_writer=writer)
            trainer.valid_epoch(sess, dataflow=valid_data, summary_writer=writer)
            
            if epoch_id % 10 == 0:
                saver.save(sess, '{}aae-epoch-{}'.format(SAVE_PATH, epoch_id))
                # if FLAGS.supervise:
                #     generator.sample_style(sess, valid_data, plot_size=10, file_id=epoch_id, n_sample=10)
                # else:
                generator.generate_samples(sess, plot_size=plot_size, file_id=epoch_id)
                if FLAGS.ncode == 2:
                    visualizer.viz_2Dlatent_variable(sess, valid_data, file_id=epoch_id)
        saver.save(sess, '{}aae-epoch-{}'.format(SAVE_PATH, epoch_id))

def generate():
    FLAGS = get_args()
    plot_size = 20

    valid_data = MNISTData('test',
                            data_dir=DATA_PATH,
                            shuffle=True,
                            pf=preprocess_im,
                            batch_dict_name=['im', 'label'])
    valid_data.setup(epoch_val=0, batch_size=FLAGS.bsize)


    generate_model = AAE(n_code=FLAGS.ncode, use_supervise=FLAGS.supervise, n_class=10)
    generate_model.create_generate_model(b_size=plot_size*plot_size)
    if FLAGS.supervise:
        generate_model.create_generate_style_model(n_sample=10)

    generator = Generator(generate_model=generate_model, save_path=SAVE_PATH,
                          distr_type=FLAGS.dist_type, n_labels=10, use_label=FLAGS.label)

    sessconfig = tf.ConfigProto()
    sessconfig.gpu_options.allow_growth = True
    with tf.Session(config=sessconfig) as sess:
        saver = tf.train.Saver()
        sess.run(tf.global_variables_initializer())
        saver.restore(sess, '{}aae-epoch-{}'.format(SAVE_PATH, FLAGS.load))
        if FLAGS.supervise:
            generator.sample_style(sess, valid_data, plot_size=10, n_sample=10)
        else:
            generator.generate_samples(sess, plot_size=plot_size)
        # generator.generate_samples(sess, plot_size=plot_size)

# def sample_style():
#     FLAGS = get_args()
#     plot_size = 20

#     valid_data = MNISTData('test',
#                             data_dir=DATA_PATH,
#                             shuffle=True,
#                             pf=preprocess_im,
#                             batch_dict_name=['im', 'label'])
#     valid_data.setup(epoch_val=0, batch_size=FLAGS.bsize)

#     model = AAE(n_code=FLAGS.ncode, use_supervise=True, n_class=10)
#     model.create_train_model()

#     generator = Generator(generate_model=model, save_path=SAVE_PATH,
#                           n_labels=10)

#     sessconfig = tf.ConfigProto()
#     sessconfig.gpu_options.allow_growth = True
#     with tf.Session(config=sessconfig) as sess:
#         saver = tf.train.Saver()
#         sess.run(tf.global_variables_initializer())
#         saver.restore(sess, '{}aae-epoch-{}'.format(SAVE_PATH, FLAGS.load))

#         generator.sample_style(sess, valid_data, n_sample=10, n_labels=10,
#                                plot_size=10, file_id=None)

def visualize():
    FLAGS = get_args()
    plot_size = 20

    valid_data = MNISTData('test',
                            data_dir=DATA_PATH,
                            shuffle=True,
                            pf=preprocess_im,
                            batch_dict_name=['im', 'label'])
    valid_data.setup(epoch_val=0, batch_size=FLAGS.bsize)

    model = AAE(n_code=FLAGS.ncode, use_label=FLAGS.label, n_class=10)
    model.create_train_model()

    valid_model = AAE(n_code=FLAGS.ncode)
    valid_model.create_generate_model(b_size=400)

    visualizer = Visualizer(model, save_path=SAVE_PATH)
    generator = Generator(generate_model=valid_model, save_path=SAVE_PATH,
                          distr_type=FLAGS.dist_type, n_labels=10, use_label=FLAGS.label)

    sessconfig = tf.ConfigProto()
    sessconfig.gpu_options.allow_growth = True
    with tf.Session(config=sessconfig) as sess:
        saver = tf.train.Saver()
        sess.run(tf.global_variables_initializer())
        saver.restore(sess, '{}aae-epoch-{}'.format(SAVE_PATH, FLAGS.load))
        visualizer.viz_2Dlatent_variable(sess, valid_data)
        generator.generate_samples(sess, plot_size=plot_size, manifold=True)

def test():
    # import matplotlib.pyplot as plt
    # import matplotlib as mpl
    # # mpl.use('Agg')
    # import src.models.ops as ops
    # real_sample = distribution.diagonal_gaussian(10000, n_dim=2, mean=0, var=1.)
    # real_sample = distribution.gaussian_mixture(
    #     10000, 2, n_labels=10, x_var=0.5, y_var=0.1, label_indices=None)
    
    # fig =plt.figure()
    # ax = fig.add_subplot(111, aspect='equal')
    # ax.scatter(real_sample[:,0], real_sample[:,1], s=3)
    # 
    # for mode_id in range(0, 10):
    #     real_sample = distribution.interpolate_gm(
    #         plot_size=20,
    #         mode_id=mode_id, n_mode=10)
    #     plt.scatter(real_sample[:,0], real_sample[:,1], s=3)

    # ax.set_xlim([-3.5, 3.5])
    # ax.set_ylim([-3.5, 3.5])
    # plt.show()


    valid_data = MNISTData('test',
                            data_dir=DATA_PATH,
                            shuffle=True,
                            pf=preprocess_im,
                            batch_dict_name=['im', 'label'],
                            n_use_label=2,
                            n_use_sample=5)
    valid_data.setup(epoch_val=0, batch_size=128)
    print(valid_data.size())
    print(valid_data.label_list)
    # batch_data = valid_data.next_batch_dict()

    # plt.figure()
    # plt.imshow(np.squeeze(batch_data['im'][0]))
    # plt.show()
    # print(batch_data['label'])

if __name__ == '__main__':
    FLAGS = get_args()

    if FLAGS.train:
        train()
    elif FLAGS.train_supervised:
        supervised_train()
    elif FLAGS.train_semisupervised:
        semisupervised_train()
    elif FLAGS.generate:
        generate()
    elif FLAGS.viz:
        visualize()
    # elif FLAGS.style:
    #     sample_style()
    elif FLAGS.test:
        test()

