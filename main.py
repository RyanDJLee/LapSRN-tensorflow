#! /usr/bin/python
# -*- coding: utf8 -*-

import os, time, random
import numpy as np
import scipy
import copy
import collections
import networkx as nx
import matplotlib.pyplot as plt
import math
import cv2

import tensorflow as tf
import tensorlayer as tl
from model import *
from utils import *
from config import *
import pprint as pp
from os import listdir
from os.path import isfile, join

###====================== HYPER-PARAMETERS ===========================###
batch_size = config.train.batch_size
patch_size = config.train.in_patch_size
ni = int(np.sqrt(config.train.batch_size))


# We only want Tensorflow to see the first GPU.
os.environ["CUDA_VISIBLE_DEVICES"]="0"


def compute_charbonnier_loss(tensor1, tensor2, is_mean=True):
    epsilon = 1e-6
    if is_mean:
        loss = tf.reduce_mean(tf.reduce_mean(tf.sqrt(tf.square(tf.subtract(tensor1,tensor2))+epsilon), [1, 2, 3]))
    else:
        loss = tf.reduce_mean(tf.reduce_sum(tf.sqrt(tf.square(tf.subtract(tensor1,tensor2))+epsilon), [1, 2, 3]))

    return loss



def load_file_list():
    train_hr_file_list = []
    train_lr_file_list = []
    valid_hr_file_list = []
    valid_lr_file_list = []

    directory = config.train.hr_folder_path
    for filename in [y for y in os.listdir(directory) if os.path.isfile(os.path.join(directory,y))]:
        train_hr_file_list.append("%s%s"%(directory,filename))

    directory = config.train.lr_folder_path
    for filename in [y for y in os.listdir(directory) if os.path.isfile(os.path.join(directory,y))]:
        train_lr_file_list.append("%s%s"%(directory,filename))

    directory = config.valid.hr_folder_path
    for filename in [y for y in os.listdir(directory) if os.path.isfile(os.path.join(directory,y))]:
        valid_hr_file_list.append("%s%s"%(directory,filename))

    directory = config.valid.lr_folder_path
    for filename in [y for y in os.listdir(directory) if os.path.isfile(os.path.join(directory,y))]:
        valid_lr_file_list.append("%s%s"%(directory,filename))

    return sorted(train_hr_file_list),sorted(train_lr_file_list),sorted(valid_hr_file_list),sorted(valid_lr_file_list)



def prepare_nn_data(hr_img_list, lr_img_list, idx_img=None):
    i = np.random.randint(len(hr_img_list)) if (idx_img is None) else idx_img

    input_image  = get_imgs_fn(lr_img_list[i])
    output_image = get_imgs_fn(hr_img_list[i])
    scale        = int(output_image.shape[0] / input_image.shape[0])
    assert scale == config.model.scale

    out_patch_size = patch_size * scale
    input_batch  = np.empty([batch_size,patch_size,patch_size,3])
    output_batch = np.empty([batch_size,out_patch_size,out_patch_size,3])

    for idx in range(batch_size):
        in_row_ind   = random.randint(0,input_image.shape[0]-patch_size)
        in_col_ind   = random.randint(0,input_image.shape[1]-patch_size)

        input_cropped = augment_imgs_fn(input_image[in_row_ind:in_row_ind+patch_size,
                                                in_col_ind:in_col_ind+patch_size])
        input_cropped = normalize_imgs_fn(input_cropped)
        input_cropped = np.expand_dims(input_cropped,axis=0)
        input_batch[idx] = input_cropped

        out_row_ind    = in_row_ind * scale
        out_col_ind    = in_col_ind * scale
        output_cropped = output_image[out_row_ind:out_row_ind+out_patch_size,
                                    out_col_ind:out_col_ind+out_patch_size]
        output_cropped = normalize_imgs_fn(output_cropped)
        output_cropped = np.expand_dims(output_cropped,axis=0)
        output_batch[idx] = output_cropped

    return input_batch,output_batch



def train():
    with tf.device('/gpu:0'):
        save_dir = "%s/%s_train"%(config.model.result_path,tl.global_flag['mode'])
        checkpoint_dir = "%s"%(config.model.checkpoint_path)
        tl.files.exists_or_mkdir(save_dir)
        tl.files.exists_or_mkdir(checkpoint_dir)

        ###========================== DEFINE MODEL ============================###
        t_image = tf.placeholder('float32', [batch_size, patch_size, patch_size, 3], name='t_image_input')
        t_target_image = tf.placeholder('float32', [batch_size, patch_size*config.model.scale, patch_size*config.model.scale, 3], name='t_target_image')
        t_target_image_down = tf.image.resize_images(t_target_image, size=[patch_size*2, patch_size*2], method=0, align_corners=False)

        net_image2, net_grad2, net_image1, net_grad1 = LapSRN(t_image, is_train=True, reuse=False)
        net_image2.print_params(False)

        ## test inference
        net_image_test, net_grad_test, _, _ = LapSRN(t_image, is_train=False, reuse=True)

        ###========================== DEFINE TRAIN OPS ==========================###
        loss2   = compute_charbonnier_loss(net_image2.outputs, t_target_image, is_mean=True)
        loss1   = compute_charbonnier_loss(net_image1.outputs, t_target_image_down, is_mean=True)
        g_loss  = loss1 + loss2 * 4
        g_vars  = tl.layers.get_variables_with_name('LapSRN', True, True)

        with tf.variable_scope('learning_rate'):
            lr_v = tf.Variable(config.train.lr_init, trainable=False)

        g_optim = tf.train.AdamOptimizer(lr_v, beta1=config.train.beta1).minimize(g_loss, var_list=g_vars)

        ###========================== RESTORE MODEL =============================###
        sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True, log_device_placement=False))
        # sess = tf.Session(config=tf.ConfigProto(log_device_placement=True))
        tl.layers.initialize_global_variables(sess)
        tl.files.load_and_assign_npz(sess=sess, name=checkpoint_dir+'/params_{}.npz'.format(tl.global_flag['mode']), network=net_image2)

        ###========================== PRE-LOAD DATA ===========================###
        train_hr_list,train_lr_list,valid_hr_list,valid_lr_list = load_file_list()

        ###========================== INTERMEDIATE RESULT ===============================###
        sample_ind = 37
        sample_input_imgs,sample_output_imgs = prepare_nn_data(valid_hr_list,valid_lr_list,sample_ind)
        tl.vis.save_images(truncate_imgs_fn(sample_input_imgs),  [ni, ni], save_dir+'/train_sample_input.png')
        tl.vis.save_images(truncate_imgs_fn(sample_output_imgs), [ni, ni], save_dir+'/train_sample_output.png')

        ###========================== TRAINING ====================###
        writer = tf.summary.FileWriter('Graphs',sess.graph)
        loss_value = tf.placeholder(tf.float32, shape=())
        # loss = tf.Variable(0.0)
        loss_summary = tf.summary.scalar('Loss', loss_value)
        sess.run(tf.assign(lr_v, config.train.lr_init))
        print(" ** learning rate: %f" % config.train.lr_init)

        for epoch in range(config.train.n_epoch):
            ## update learning rate
            if epoch != 0 and (epoch % config.train.decay_iter == 0):
                lr_decay = config.train.lr_decay ** (epoch // config.train.decay_iter)
                lr = config.train.lr_init * lr_decay
                sess.run(tf.assign(lr_v, lr))
                print(" ** learning rate: %f" % (lr))

            epoch_time = time.time()
            total_g_loss, n_iter = 0, 0

            ## load image data
            idx_list = np.random.permutation(len(train_hr_list))
            for idx_file in range(len(idx_list)):
                step_time = time.time()
                batch_input_imgs,batch_output_imgs = prepare_nn_data(train_hr_list,train_lr_list,idx_file)
                errM, _ = sess.run([g_loss, g_optim], {t_image: batch_input_imgs, t_target_image: batch_output_imgs})
                total_g_loss += errM
                n_iter += 1

            loss = total_g_loss/n_iter
            print("[*] Epoch: [%2d/%2d] time: %4.4fs, loss: %.8f" % (epoch, config.train.n_epoch, time.time() - epoch_time, loss))

            s_ = sess.run(loss_summary, feed_dict={loss_value : loss})
            writer.add_summary(s_, epoch)
            writer.flush()

            ## save model and evaluation on sample set
            if (epoch >= 0):
                tl.files.save_npz(net_image2.all_params,  name=checkpoint_dir+'/params_{}.npz'.format(tl.global_flag['mode']), sess=sess)
                saver = tf.train.Saver(tf.global_variables())

                if config.train.dump_intermediate_result is True:
                    sample_out, sample_grad_out = sess.run([net_image_test.outputs,net_grad_test.outputs], {t_image: sample_input_imgs})#; print('gen sub-image:', out.shape, out.min(), out.max())
                    tl.vis.save_images(truncate_imgs_fn(sample_out), [ni, ni], save_dir+'/train_predict_%d.png' % epoch)
                    tl.vis.save_images(truncate_imgs_fn(np.abs(sample_grad_out)), [ni, ni], save_dir+'/train_grad_predict_%d.png' % epoch)


# TODO: Extend test function to run the model on all test data in BSDS100 and then calculate all the PSNR values per image?
def test(file):
    try:
        img = get_imgs_fn(file)
    except IOError:
        print('cannot open %s'%(file))
    else:
        checkpoint_dir = config.model.checkpoint_path
        save_dir = "%s/%s"%(config.model.result_path,tl.global_flag['mode'])
        input_image = normalize_imgs_fn(img)

        size = input_image.shape
        print('Input size: %s,%s,%s'%(size[0],size[1],size[2]))
        t_image = tf.placeholder('float32', [None,size[0],size[1],size[2]], name='input_image')
        net_g, _, _, _ = LapSRN(t_image, is_train=False, reuse=False)

        ###========================== RESTORE G =============================###
        sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True, log_device_placement=False))
        tl.layers.initialize_global_variables(sess)
        tl.files.load_and_assign_npz(sess=sess, name=checkpoint_dir+'/params_train.npz', network=net_g)

        ###======================= TEST =============================###
        start_time = time.time()
        out = sess.run(net_g.outputs, {t_image: [input_image]})
        print("took: %4.4fs" % (time.time() - start_time))



        tl.files.exists_or_mkdir(save_dir)
        tl.vis.save_image(truncate_imgs_fn(out[0,:,:,:]), save_dir+'/test_out.png')
        tl.vis.save_image(input_image, save_dir+'/test_input.png')


def _psnr(img1, img2):
    mse = np.mean( (img1 - img2) ** 2 )
    if mse == 0:
        return 100
    PIXEL_MAX = 255.0
    return 20 * math.log10(PIXEL_MAX / math.sqrt(mse))


def test_dir(test_path, x4_path):
    """
    """
    with tf.device('/cpu:0'):
        psnr_dict = {}
        checkpoint_dir = config.model.checkpoint_path
        save_dir = "%s/%s"%(config.model.result_path,tl.global_flag['mode'])
        # Get files in directory.
        # TODO: Sort then zip to optimize?

        images = [f[:-7] for f in listdir(test_path) if isfile(join(test_path, f))]

        for file in images:
            img = get_imgs_fn(test_path+'/'+file+'_LR.png')

            input_image = normalize_imgs_fn(img)

            size = input_image.shape
            print('Input size: %s,%s,%s'%(size[0],size[1],size[2]))
            t_image = tf.placeholder('float32', [None,size[0],size[1],size[2]], name='input_image')
            net_g, _, _, _ = LapSRN(t_image, is_train=False, reuse=tf.AUTO_REUSE)

            ###========================== RESTORE G =============================###
            sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True, log_device_placement=False))
            tl.layers.initialize_global_variables(sess)
            tl.files.load_and_assign_npz(sess=sess, name=checkpoint_dir+'/params_train.npz', network=net_g)

            ###======================= TEST =============================###
            start_time = time.time()
            out = sess.run(net_g.outputs, {t_image: [input_image]})
            print("took: %4.4fs" % (time.time() - start_time))


            tl.files.exists_or_mkdir(save_dir)
            out_img = truncate_imgs_fn(out[0,:,:,:])
            tl.vis.save_image(out_img, save_dir+'/'+'out_'+file+'.png')
            # tl.vis.save_image(input_image, save_dir+'/'+'in_'+file)
            psnr_dict[file[:-4]] = _psnr(get_imgs_fn(x4_path+'/'+file+'_HR.png'), out_img)


        with open(save_dir + '/output.txt', 'wt') as out:
            pp.pprint(psnr_dict, stream=out)
        pp.pprint(psnr_dict)


###====== Extract pre-trained Network's Weights to CSV ======###
# TODO: Ahh..do not use an empty list as the default..
def _extract_values(img, params=[]):
    """Return a dictionary of parameter names and values give a test image,
    output directory and parameter name(s).
    """
    try:
        img = get_imgs_fn(img)
    except IOError:
        print('cannot open %s'%(img))
    else:
        checkpoint_dir = config.model.checkpoint_path
        input_image = normalize_imgs_fn(img)

        size = input_image.shape
        t_image = tf.placeholder('float32', [None,size[0],size[1],size[2]], name='input_image')
        net_g, _, _, _ = LapSRN(t_image, is_train=False, reuse=False)

        sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True, log_device_placement=False))
        tl.layers.initialize_global_variables(sess)
        # TODO: Parameterize although name should be an invariant given this training model?
        tl.files.load_and_assign_npz(sess=sess, name=checkpoint_dir+'/params_train.npz', network=net_g)
        # Grab all parameter values.
        param_tensors = []
        if not params:
            param_tensors = [v for v in tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES)]
        else:
            tfs_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES)
            for param in params:
                # Find the tf variable
                param_tensors.append(tfs_vars[[v.name for v in tfs_vars].index(param)])

        values_dict = collections.OrderedDict()

        for param_t in param_tensors:
            # TODO: Optimize?
            # values_dict[param] = sess.run([v for v in tf.global_variables() if v.name == params[0]][0])
            values_dict[param_t.name] = sess.run(param_t)[0]
        # For debugging colouring
        # values_dict['LapSRN/init_conv/W_conv2d:0'] = values_dict['LapSRN/Model_level/conv_D0/W_conv2d:0']
        # values_dict['LapSRN/Model_level/conv_D9/W_conv2d:0'] = values_dict['LapSRN/Model_level/conv_D8/W_conv2d:0']
        return values_dict


# TODO: enforce order of image and output file?
def extract_params(img, output_file, params):
    # TODO: Just save?
    """Display and save a values dictionary of specified parameter(s) given a test image,
    output directory and parameter names.
    """
    if not params:
        print('Extracting all Parameter Values!')
    else:
        print('Extracting Parameter Values for: {params}'.format(params=params))
    print('\n\n\n')
    values_dict = _extract_values(img, params=params)
    pp.pprint(values_dict)

    file = open(output_file, 'w')
    file.write(str(values_dict))
    file.close()


def _flatten_values(tensor_values):
    """Return flattened list of values given tensor's values.
    """
    if isinstance(tensor_values, collections.Iterable):
        return [a for b in tensor_values for a in _flatten_values(b)]
    else:
        return [tensor_values]


def _get_shape(weights):
    shape = []
    if isinstance(weights, collections.Iterable):
        shape.append(len(weights))
        shape.extend(_get_shape(weights[0]))
    else:
        shape.append(-1)
    x = copy.deepcopy(shape)
    return x


def analyze_layers(img, output_dir, mode):
    """Display parameter sharing between layers and save ouput to specified output directory.
    """
    # TODO: Could be/should be doing this work in _extract. Rethink design and refactor?
    values_dict = _extract_values(img)
    weight_keys = [key for key in values_dict.keys() if key[key.rfind('/') + 1] == 'W']
    # TODO: Save memory or computation?
    # flattened_dict = copy.deepcopy(values_dict)
    flattened_dict = {}
    for k in weight_keys:
        flattened_dict[k] = _flatten_values(values_dict[k])

    if mode == 'text':
        i = 1
        colour = {k : '' for k in weight_keys}
        shape = _get_shape(list(values_dict.values())[0])[:-1]
        # shape = '(' + ','.join(map(str, _get_shape(list(values_dict.values())[0]))) + ')'
        for w1 in weight_keys:
            for w2 in weight_keys:
                if flattened_dict[w1] == flattened_dict[w2] and w1 != w2:
                    if colour[w1] == '' and colour[w2] == '':
                        colour[w1] = '\x1b[6;3' + str(i) + ';42m'
                        i += 2
                    elif colour[w2] != '':
                        colour[w1] = colour[w2]
                    else:
                        colour[w2] = colour[w1]
        output = ''
        for w in weight_keys:
            if colour[w] == '':
                output += w + '\t' + shape.__repr__() + '\n'
            else:
                output += colour[w] + w + '\x1b[0m' + '\t' + shape.__repr__() + '\n'
        print(output)
    else:
        for k in weight_keys:
            flattened_dict[k] = _flatten_values(values_dict[k])
        layer_graph = nx.Graph()
        layer_graph.add_nodes_from(weight_keys)
        for w1 in weight_keys:
            for w2 in weight_keys:
                if flattened_dict[w1] == flattened_dict[w2] and ((w2, w1) not in list(layer_graph.edges)) and w1 != w2:
                    layer_graph.add_edge(w1, w2)
        nx.draw(layer_graph, with_labels=True, font_weight='bold')
        plt.savefig(output_dir + '/shared_parameter_graph.png', dpi=500, format="PNG")
        plt.show()

    print('\x1b[6;30;42m' + 'Success!' + '\x1b[0m')



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--mode', choices=['train','test', 'test_dir', 'extract', 'analyze', 'losses'],
                        default='train', help='select mode')
    # TODO: Do len check for other methods
    parser.add_argument('-f', '--file', nargs='+', help='input file')
    parser.add_argument('-p', '--parameters', nargs='+', help='input parameter name(s)')
    parser.add_argument('-o', '--output', choices=['text', 'graph'], help='input desired output format')

    args = parser.parse_args()

    tl.global_flag['mode'] = args.mode
    if tl.global_flag['mode'] == 'train':
        train()
    elif tl.global_flag['mode'] == 'test':
        if (args.file is None):
            raise Exception("Please enter input file name for test mode")
        test(args.file)
    elif tl.global_flag['mode'] == 'test_dir':
        test_dir(args.file[0], args.file[1])
    # TODO: Shouldn't the network be the same regardless of test image?
    elif tl.global_flag['mode'] == 'extract':
        # TODO: Error handling
        extract_params(args.file[0], args.file[1], args.parameters)
    elif tl.global_flag['mode'] == 'analyze':
        # TODO: Error handling
        analyze_layers(args.file[0], args.file[1], args.output)
    elif tl.global_flag['mode'] == 'losses':
        get_losses()
    else:
        raise Exception("Unknow --mode")
