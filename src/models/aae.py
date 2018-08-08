#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: aae.py
# Author: Qian Ge <geqian1001@gmail.com>

import tensorflow as tf
from src.models.base import BaseModel
import src.models.layers as L
import src.models.modules as modules
import src.models.ops as ops

# INIT_W = tf.keras.initializers.he_normal()
INIT_W = tf.contrib.layers.variance_scaling_initializer()
# INIT_W = tf.random_normal_initializer(mean=0., stddev=0.01)

class AAE(BaseModel):
    def __init__(self, im_size=[28, 28], n_code=1000, n_channel=1, wd=0,
                 use_label=False, n_class=None, use_supervise=False, add_noise=False,
                 enc_weight=1., gen_weight=1., dis_weight=1.,
                 cat_dis_weight=1., cat_gen_weight=1., cls_weight=1.):
        self._n_channel = n_channel
        self._wd = wd
        self.n_code = n_code
        self._im_size = im_size
        if use_supervise:
            use_label = False
        self._flag_label = use_label
        self._flag_supervise = use_supervise
        self._flag_noise = add_noise
        self.n_class = n_class
        self._enc_w = enc_weight
        self._gen_w = gen_weight
        self._dis_w = dis_weight
        self._cat_dis_w = cat_dis_weight
        self._cat_gen_w = cat_gen_weight
        self._cls_w = cls_weight
        self.layers = {}

    def create_generate_style_model(self, n_sample):
        self.set_is_training(False)
        with tf.variable_scope('AE', reuse=tf.AUTO_REUSE):
            self._create_generate_input()
            label = []
            for i in range(self.n_class):
                label.extend([i for k in range(n_sample)])
            label = tf.convert_to_tensor(label) # [n_class]
            one_hot_label = tf.one_hot(label, self.n_class) # [n_class*n_sample, n_class]

            encoder_out = self.encoder(self.image)
            z, z_mu, z_std, z_log_std = self.sample_latent(encoder_out)
            z = tf.tile(z, [n_sample, 1]) # [n_class*n_sample, n_code]
            decoder_in = tf.concat((z, one_hot_label), axis=-1)
            self.layers['generate_style'] = (self.decoder(decoder_in) + 1. ) / 2.

    def create_generate_model(self, b_size):
        self.set_is_training(False)
        with tf.variable_scope('AE', reuse=tf.AUTO_REUSE):
            self._create_generate_input()
            self.z = ops.tf_sample_standard_diag_guassian(b_size, self.n_code)
            decoder_in = self.z
            if self._flag_supervise:
                label = []
                for i in range(self.n_class):
                    label.extend([i for k in range(10)])
            #     # label = [i for i in range(self.n_class)]
                label = tf.convert_to_tensor(label) # [n_class]
                one_hot_label = tf.one_hot(label, self.n_class) # [n_class*10, n_class]
            #     # one_hot_label = tf.tile(one_hot_label, [10, 1]) # [n_class*10, n_class]
            #     # one_hot_label = tf.transpose()
                # encoder_out = self.encoder(self.image)
                # z, z_mu, z_std, z_log_std = self.sample_latent(encoder_out)
                choose_code = decoder_in[:self.n_class] # [n_class, n_code]
                z = tf.tile(choose_code, [10, 1]) # [n_class*10, n_code]
                decoder_in = tf.concat((z, one_hot_label), axis=-1)
            self.layers['generate'] = (self.decoder(decoder_in) + 1. ) / 2.
            # self.layers['generate'] = tf.nn.sigmoid(self.decoder(self.z))

    def _create_generate_input(self):
        self.z = tf.placeholder(
            tf.float32, name='latent_z',
            shape=[None, self.n_code])
        self.keep_prob = 1.
        self.image = tf.placeholder(
            tf.float32, name='image',
            shape=[None, self._im_size[0], self._im_size[1], self._n_channel])

    def _create_cls_input(self):
        self.keep_prob = 1.
        self.label = tf.placeholder(tf.int64, name='label', shape=[None])
        self.image = tf.placeholder(
            tf.float32, name='image',
            shape=[None, self._im_size[0], self._im_size[1], self._n_channel])

    def create_semisupervised_test_model(self):
        self.set_is_training(False)
        self._create_cls_input()
        with tf.variable_scope('AE', reuse=tf.AUTO_REUSE):
            encoder_in = self.image
            self.encoder_in = encoder_in
            self.layers['encoder_out'] = self.encoder(self.encoder_in)
            # discrete class variable
            self.layers['cls_logits'] = self.cls_layer(self.layers['encoder_out'])
            self.layers['y'] = tf.argmax(self.layers['cls_logits'], axis=-1,
                                         name='label_predict')
        # create cls_loss node for validation
        self.lr = 1
        self.get_semisupervised_train_op()


    def create_semisupervised_train_model(self):
        self.set_is_training(True)
        self._create_train_input()
        with tf.variable_scope('AE', reuse=tf.AUTO_REUSE):
            encoder_in = self.image
            if self._flag_noise:
                encoder_in += tf.random_normal(
                    tf.shape(encoder_in),
                    mean=0.0,
                    stddev=0.6,
                    dtype=tf.float32)
            self.encoder_in = encoder_in
            self.layers['encoder_out'] = self.encoder(self.encoder_in)
            # continuous latent variable
            self.layers['z'], self.layers['z_mu'], self.layers['z_std'], self.layers['z_log_std'] =\
                self.sample_latent(self.layers['encoder_out'])
            # discrete class variable
            self.layers['cls_logits'] = self.cls_layer(self.layers['encoder_out'])
            # self.layers['y'] = tf.multinomial(self.layers['cls_logits'], num_samples=1,
            #                                   name='sample_y')

            self.layers['y'] = tf.argmax(self.layers['cls_logits'], axis=-1,
                                         name='label_predict')
            self.layers['one_hot_y_approx'] = tf.nn.softmax(self.layers['cls_logits'], axis=-1)
            # one_hot_y = self.layers['cls_logits'] 

            decoder_in = tf.concat((self.layers['z'], self.layers['one_hot_y_approx']), axis=-1)
            self.layers['decoder_out'] = self.decoder(decoder_in)
            self.layers['sample_im'] = (self.layers['decoder_out'] + 1. ) / 2.

        with tf.variable_scope('regularization_z'):
            fake_in = self.layers['z']
            real_in = self.real_distribution
            self.layers['fake_z'] = self.discriminator(fake_in)
            self.layers['real_z'] = self.discriminator(real_in)

        with tf.variable_scope('regularization_y'):
            fake_in = self.layers['one_hot_y_approx']
            real_in = tf.one_hot(self.real_y, self.n_class)
            self.layers['fake_y'] = self.cat_discriminator(fake_in)
            self.layers['real_y'] = self.cat_discriminator(real_in)

    def create_train_model(self):
        self.set_is_training(True)
        self._create_train_input()
        with tf.variable_scope('AE', reuse=tf.AUTO_REUSE):
            encoder_in = self.image
            if self._flag_noise:
                encoder_in += tf.random_normal(
                    tf.shape(encoder_in),
                    mean=0.0,
                    stddev=0.6,
                    dtype=tf.float32)
            self.encoder_in = encoder_in
            self.layers['encoder_out'] = self.encoder(self.encoder_in)
            self.layers['z'], self.layers['z_mu'], self.layers['z_std'], self.layers['z_log_std'] =\
                self.sample_latent(self.layers['encoder_out'])

            self.decoder_in = self.layers['z']
            if self._flag_supervise:
                one_hot_label = tf.one_hot(self.label, self.n_class)
                decoder_in = tf.concat((self.decoder_in, one_hot_label), axis=-1)
            self.layers['decoder_out'] = self.decoder(decoder_in)
            self.layers['sample_im'] = (self.layers['decoder_out'] + 1. ) / 2.

        with tf.variable_scope('regularization_z'):
            fake_in = self.layers['z']
            real_in = self.real_distribution
            self.layers['fake_z'] = self.discriminator(fake_in)
            self.layers['real_z'] = self.discriminator(real_in)
        
    def _create_train_input(self):
        self.image = tf.placeholder(
            tf.float32, name='image',
            shape=[None, self._im_size[0], self._im_size[1], self._n_channel])
        self.label = tf.placeholder(
            tf.int64, name='label', shape=[None])
        self.real_distribution = tf.placeholder(
            tf.float32, name='real_distribution', shape=[None, self.n_code])
        self.real_y = tf.placeholder(
            tf.int64, name='real_y', shape=[None])
        self.lr = tf.placeholder(tf.float32, name='lr')
        self.keep_prob = tf.placeholder(tf.float32, name='keep_prob')

    def encoder(self, inputs):
        with tf.variable_scope('encoder'):
            # cnn_out = modules.encoder_CNN(
            #     self.image, is_training=self.is_training, init_w=INIT_W,
            #     wd=self._wd, bn=False, name='encoder_CNN')

            fc_out = modules.encoder_FC(inputs, self.is_training, keep_prob=self.keep_prob, wd=self._wd, name='encoder_FC', init_w=INIT_W)

            # fc_out = L.linear(
            #     out_dim=self.n_code*2, layer_dict=self.layers,
            #     inputs=cnn_out, init_w=INIT_W, wd=self._wd, name='Linear')

            return fc_out

    def cls_layer(self, encoder_out):
        cls_logits = L.linear(
            out_dim=self.n_class, layer_dict=self.layers,
            inputs=encoder_out, init_w=INIT_W, wd=self._wd, name='cls_layer')
        return cls_logits

    def sample_latent(self, encoder_out):
        with tf.variable_scope('sample_latent'):
            encoder_out = encoder_out
            
            z_mean = L.linear(
                out_dim=self.n_code, layer_dict=self.layers,
                inputs=encoder_out, init_w=INIT_W, wd=self._wd, name='latent_mean')
            z_std = L.linear(
                out_dim=self.n_code, layer_dict=self.layers, nl=L.softplus,
                inputs=encoder_out, init_w=INIT_W, wd=self._wd, name='latent_std')
            z_log_std = tf.log(z_std + 1e-8)

            b_size = tf.shape(encoder_out)[0]
            z = ops.tf_sample_diag_guassian(z_mean, z_std, b_size, self.n_code)
            return z, z_mean, z_std, z_log_std

    def decoder(self, inputs):
        with tf.variable_scope('decoder'):

            fc_out = modules.decoder_FC(inputs, self.is_training, keep_prob=self.keep_prob,
                                        wd=self._wd, name='decoder_FC', init_w=INIT_W)
            out_dim = self._im_size[0] * self._im_size[1] * self._n_channel
            decoder_out = L.linear(
                out_dim=out_dim, layer_dict=self.layers,
                inputs=fc_out, init_w=None, wd=self._wd, name='decoder_linear')
            decoder_out = tf.reshape(decoder_out, (-1, self._im_size[0], self._im_size[1], self._n_channel))

            return tf.tanh(decoder_out)

    def discriminator(self, inputs):
        with tf.variable_scope('latent_discriminator', reuse=tf.AUTO_REUSE):
            fc_out = modules.discriminator_FC(inputs, self.is_training,
                                              nl=L.leaky_relu,
                                              wd=self._wd, name='latent_discriminator_FC',
                                              init_w=INIT_W)
            return fc_out

    def cat_discriminator(self, inputs):
        with tf.variable_scope('cat_discriminator', reuse=tf.AUTO_REUSE):
            fc_out = modules.discriminator_FC(inputs, self.is_training,
                                              nl=L.leaky_relu,
                                              wd=self._wd, name='cat_discriminator_FC',
                                              init_w=INIT_W)
            return fc_out

    def sample_prior(self):
        b_size = tf.shape(self.image)[0]
        samples = ops.tf_sample_standard_diag_guassian(b_size, self.n_code)
        return samples

    def _get_loss(self):
        with tf.name_scope('reconstruction_loss'):
            p_hat = self.layers['decoder_out']
            p = self.image
            autoencoder_loss = 0.5 * tf.reduce_mean(tf.reduce_sum(tf.square(p - p_hat), axis=[1,2,3]))

            return autoencoder_loss * self._enc_w

    # def _get_optimizer(self):
    #     return tf.train.AdamOptimizer(self.lr, beta1=0.5)
        # return tf.train.MomentumOptimizer(self.lr, momentum=0.9)

    def get_train_op(self):
        with tf.name_scope('train'):
            opt = tf.train.AdamOptimizer(self.lr, beta1=0.5)
            loss = self.get_loss()
            var_list = tf.trainable_variables(scope='AE')
            print(var_list)
            grads = tf.gradients(loss, var_list)
            return opt.apply_gradients(zip(grads, var_list))

    def get_latent_generator_train_op(self):
        var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/encoder') +\
                   tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/sample_latent')
        self.latent_g_loss, train_op = modules.train_generator(
            fake_in=self.layers['fake_z'],
            loss_weight=self._gen_w,
            opt=tf.train.AdamOptimizer(self.lr, beta1=0.5),
            # lr=self.lr,
            var_list=var_list,
            name='z_generate_train_op')
        return train_op

    def get_cat_generator_train_op(self):
        var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/encoder') +\
                   tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/cls_layer')
        self.cat_g_loss, train_op = modules.train_generator(
            fake_in=self.layers['fake_y'],
            loss_weight=self._cat_gen_w,
            opt=tf.train.AdamOptimizer(self.lr, beta1=0.5),
            # lr=self.lr,
            var_list=var_list,
            name='y_generate_train_op')
        return train_op
        # with tf.name_scope('generator_train_op'):
        #     with tf.name_scope('generator_loss'):
        #         gan_loss = tf.nn.sigmoid_cross_entropy_with_logits(
        #             labels=tf.ones_like(self.layers['fake']),
        #             logits=self.layers['fake'],
        #             name='output')
        #         self.gan_loss = tf.reduce_mean(gan_loss)
        #     opt = tf.train.AdamOptimizer(self.lr, beta1=0.5)
        #     # opt = tf.train.MomentumOptimizer(self.lr, momentum=0.1)
        #     # var_list = tf.trainable_variables(scope=['AE/encoder'])
        #     var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/encoder') +\
        #                tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/sample_latent')
        #     print(var_list)
        #     grads = tf.gradients(self.gan_loss * self._gen_w, var_list)
        #     return opt.apply_gradients(zip(grads, var_list))

    def get_latent_discrimator_train_op(self):
        self.latent_d_loss, train_op = modules.train_discrimator(
            fake_in=self.layers['fake_z'],
            real_in=self.layers['real_z'],
            loss_weight=self._dis_w,
            opt=tf.train.AdamOptimizer(self.lr, beta1=0.5),
            # lr=self.lr,
            var_list=tf.trainable_variables(scope='regularization_z'),
            name='z_discrimator_train_op')
        return train_op

    def get_cat_discrimator_train_op(self):
        self.cat_d_loss, train_op = modules.train_discrimator(
            fake_in=self.layers['fake_y'],
            real_in=self.layers['real_y'],
            loss_weight=self._cat_dis_w,
            opt=tf.train.AdamOptimizer(self.lr, beta1=0.5),
            # lr=self.lr,
            var_list=tf.trainable_variables(scope='regularization_y'),
            name='y_discrimator_train_op')
        return train_op

    def get_semisupervised_train_op(self):
        var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/encoder') +\
                   tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/cls_layer')
        self.cls_loss, train_op  = modules.train_by_cross_entropy_loss(
            logits=self.layers['cls_logits'],
            labels=self.label,
            loss_weight=self._cls_w,
            opt=tf.train.AdamOptimizer(self.lr, beta1=0.5),
            var_list=var_list,
            name='semisupervised_train_op')
        return train_op

        # with tf.name_scope('semisupervised_train_op'):
        #     with tf.name_scope('cls_loss'):
        #         logits = self.layers['cls_logits']
        #         labels = self.label
        #         cross_entropy = tf.nn.sigmoid_cross_entropy_with_logits(
        #             labels=labels,
        #             logits=logits,
        #             name='cross_entropy')
        #         loss = tf.reduce_mean(cross_entropy)
        #         self.cls_loss = loss

        #     var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/encoder') +\
        #            tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='AE/cls_layer')
        #     opt = tf.train.AdamOptimizer(self.lr, beta1=0.5)
        #     grads = tf.gradients(self.cls_loss * loss_weight, var_list)
        #     train_op = opt.apply_gradients(zip(grads, var_list))


        # with tf.name_scope('discrimator_train_op'):
        #     with tf.name_scope('discrimator_loss'):
        #         loss_real = tf.nn.sigmoid_cross_entropy_with_logits(
        #             labels=tf.ones_like(self.layers['real']),
        #             logits=self.layers['real'],
        #             name='loss_real')
        #         loss_fake = tf.nn.sigmoid_cross_entropy_with_logits(
        #             labels=tf.zeros_like(self.layers['fake']),
        #             logits=self.layers['fake'],
        #             name='loss_fake')
        #         d_loss = tf.reduce_mean(loss_real) + tf.reduce_mean(loss_fake)
        #         self.d_loss = d_loss
                
        #     opt = tf.train.AdamOptimizer(self.lr, beta1=0.5)
        #     # opt = tf.train.MomentumOptimizer(self.lr, momentum=0.1)
        #     # dc_var = [var for var in all_variables if 'dc_' in var.name]
        #     var_list = tf.trainable_variables(scope='discriminator')
        #     # print(tf.trainable_variables())
        #     print(var_list)
        #     grads = tf.gradients(self.d_loss * self._gen_w, var_list)
        #     # [tf.summary.histogram('gradient/' + var.name, grad, 
        #     #  collections=['train']) for grad, var in zip(grads, var_list)]
        #     return opt.apply_gradients(zip(grads, var_list))

    def get_cls_accuracy(self):
        with tf.name_scope('cls_accuracy'):
            labels = self.label
            cls_predict = self.layers['y']
            num_correct = tf.cast(tf.equal(labels, cls_predict), tf.float32)
            return tf.reduce_mean(num_correct)

    def get_generate_summary(self):
        with tf.name_scope('generate'):
            tf.summary.image(
                'image',
                tf.cast(self.layers['generate'], tf.float32),
                collections=['generate'])
        return tf.summary.merge_all(key='generate')

    def get_valid_summary(self):
        with tf.name_scope('valid'):
            tf.summary.image(
                'encoder input',
                tf.cast(self.encoder_in, tf.float32),
                collections=['valid'])
            tf.summary.image(
                'decoder output',
                tf.cast(self.layers['sample_im'], tf.float32),
                collections=['valid'])  
            return tf.summary.merge_all(key='valid')

    def get_train_summary(self):
        with tf.name_scope('train'):
            tf.summary.image(
                'input image',
                tf.cast(self.image, tf.float32),
                collections=['train'])
            tf.summary.image(
                'encoder input',
                tf.cast(self.encoder_in, tf.float32),
                collections=['train'])
            tf.summary.image(
                'decoder output',
                tf.cast(self.layers['sample_im'], tf.float32),
                collections=['train'])

            tf.summary.histogram(
                name='z real distribution', values=self.real_distribution,
                collections=['train'])
            tf.summary.histogram(
                name='z encoder distribution', values=self.layers['z'],
                collections=['train'])
            try:
                tf.summary.histogram(
                    name='y real distribution', values=self.real_y,
                    collections=['train'])
                tf.summary.histogram(
                    name='y encoder distribution', values=self.layers['y'],
                    collections=['train'])
            except AttributeError:
                pass
        # var_list = tf.trainable_variables()
        # [tf.summary.histogram('gradient/' + var.name, grad, 
        #  collections=['train']) for grad, var in zip(grads, var_list)]
        
        return tf.summary.merge_all(key='train')

