# -*- coding: utf-8 -*-
"""Multi purpose implementation of a U-Net

This script is an implementation of the U-Net proposed in [1]. It features some
tweaks to improve classification and training/testing/prediction speed, namely:
    * residual links - instead of being regular identity links, links can have
    a residual architecture [2]. This involves branching the link into two
    layers, one carrying the identity and the other performing two convolutions
    in a parallel fashion and summing both of them in the end;
    * convolution factorization - convolutions can be factorized to improve
    speed [3]. This means that instead of performing 9 operations in a 3x3
    convolution, the network only needs to perform 6 operations by factorizing
    the 3x3 convolution into a 1x3 convolution followed by a 3x1 convolution
    (or vice-versa);
    * Iglovikov loss function - instead of using the standard function for
    cross entropy, an extra non-differentiable term used to measure
    segmentation quality, the Jaccard Index (or Intersection Over Union - IOU),
    is added to the loss function [4].

Training example:
    $ python3 u-net.py --dataset_dir split_512/train/input/ \
    --truth_dir split_512/train/truth/ \
    --padding SAME \
    --batch_size 4 \
    --log_every_n_steps 5 \
    --input_height 512 \
    --input_width 512 \
    --n_classes 2 \
    --number_of_steps 3120 \
    --save_checkpoint_folder split_512/checkpoint_residuals \
    --save_summary_folder split_512/summary_residuals \
    --factorization \
    --residuals

Help:
    $ python3 u-net.py -h

[1] https://arxiv.org/abs/1505.04597
[2] https://arxiv.org/abs/1512.03385
[3] https://arxiv.org/abs/1512.00567
[4] https://arxiv.org/pdf/1706.06169"""

import argparse
import warnings
import os
from sklearn import metrics
from unet_utilities import *

warnings.filterwarnings("ignore", category=DeprecationWarning)

#Defining functions

class ToDirectory(argparse.Action):
    """
    Action class to use as in add_argument to automatically return the absolute
    path when a path input is provided.
    """
    def __init__(self, option_strings, dest, **kwargs):
        super(ToDirectory, self).__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, os.path.abspath(values))

def main(mode,
         log_file,
         log_every_n_steps,
         save_summary_steps,
         save_summary_folder,
         save_checkpoint_steps,
         save_checkpoint_folder,
         squeeze_and_excite,
         iglovikov,
         batch_size,
         number_of_steps,
         epochs,
         acl,
         beta_l2_regularization,
         learning_rate,
         factorization,
         residuals,
         weighted,
         depth_mult,
         truth_only,
         checkpoint_path,
         prediction_output,
         large_prediction_output,
         data_augmentation_params,
         dataset_dir,
         path_csv,
         truth_dir,
         padding,
         extension,
         input_height,
         input_width,
         n_classes,
         trial,
         aux_node):

    """
    Wraper for the entire script.

    Arguments:
    * log_file - path to the log file
    * log_every_n_steps - how often should a log be produced
    * save_summary_steps - how often should the summary be updated
    * save_summary_folder - where shold the summary be saved
    * save_checkpoint_steps - how often should checkpoints be saved
    * save_checkpoint_folder - where should checkpoints be saved
    * iglovikov - whether the Iglovikov loss should be used
    * batch_size - number of images *per* training batch
    * number_of_steps - number of iterations
    * epochs - number of epochs (overrides number of steps)
    * acl - active contour loss from "Learning Active Contour Models for
    Medical Image Segmentation" (proportion)
    * beta_l2_regularization - L2 regularization factor for the loss
    * learning_rate - learning rate for the training
    * factorization - whether or not convolutions should be factorized
    * residuals - whether residual linkers in the shortcut connections should
    be used
    * weighted - whether weight maps should be calculated
    * depth_mult - a multiplier for the depth of the layers
    * truth_only - whether only positive images should be used
    * mode - algorithm mode.
    * checkpoint_path - path to the checkpoint to restore
    * prediction_output - where the predicted output should be stored
    * large_prediction_output - where the large image predictions should be
    stored
    * noise_chance - probability of corrupting the image with random noise
    * blur_chance - probability of blurring the image
    * flip_chance - probability of rotating the image
    * resize - whether the input image should be resized
    * resize_height - height of the resized image
    * resize_width - width of the resized image
    * dataset_dir - directory containing the image dataset
    * truth_dir - directory containing the truth images
    * padding - whether the images should have 'VALID' or 'SAME' padding
    * extension - extension for the images
    * input_height - height of the input image
    * input_width - width of the input image
    * n_classes - no. of classes (currently only supports 2/3)
    """

    log_write_print(log_file,'INPUT ARGUMENTS:')
    for var in vars(args):
        log_write_print(log_file,'\t{0}={1}'.format(var,vars(args)[var]))
    print('\n')

    print("Preparing the network...\n")

    if dataset_dir != None:
        image_path_list = glob(dataset_dir + '/*' + extension)

    if path_csv != None:
        with open(path_csv) as o:
            lines = o.readlines()
        image_path_list = []
        for line in lines[1:]:
            tmp = line.strip().split(',')
            if len(tmp) == 3:
                if tmp[2] == '1':
                    image_path_list.append(tmp[1])
        image_path_list = list(set(image_path_list))

    if extension == 'h5':
        hdf5_path = dataset_dir

    if trial:
        image_path_list = image_path_list[:50]

    if mode == 'train':
        is_training = True
        output_types = (tf.uint8,tf.float32,tf.float32)
        output_shapes = (
            [input_height,input_width,3],
            [input_height,input_width,n_classes],
            [input_height,input_width,1])
    elif 'test' in mode:
        is_training = False
        output_types = (tf.uint8,tf.float64)
        output_shapes = (
            [input_height,input_width,3],
            [input_height,input_width,n_classes]
            )
    elif 'predict' in mode:
        is_training = False
        output_types = tf.uint8,tf.string
        output_shapes = ([input_height,input_width,3],[])
    elif mode == 'large_predict':
        is_training = False
        output_types = (tf.uint8,tf.string,tf.int32,tf.int32)
        output_shapes = ([input_height,input_width,3],[],[2],[])

    if np.all([extension == 'tfrecord',
               dataset_dir != None,
               mode in ['train','test']]):
        def parse_example(serialized_example):
            feature = {
                'image': tf.FixedLenFeature([], tf.string),
                'mask': tf.FixedLenFeature([], tf.string),
                'weight_mask': tf.FixedLenFeature([], tf.string),
                'image_name': tf.FixedLenFeature([], tf.string),
                'classification': tf.FixedLenFeature([], tf.int64)
            }
            features = tf.parse_single_example(serialized_example,
                                               features=feature)
            image = tf.decode_raw(
                features['image'],tf.uint8)
            mask = tf.decode_raw(
                features['mask'],tf.uint8)
            weights = tf.decode_raw(
                features['weight_mask'],tf.float64)

            image = tf.reshape(image,[input_height, input_width, 3])
            mask = tf.reshape(mask,[input_height, input_width, n_classes])
            weights = tf.reshape(weights,[input_height, input_width, 1])
            weights = tf.cast(weights,tf.float32)
            return image,mask,weights

        def predicate(image,mask,weights):
            return tf.greater(tf.reduce_sum(mask),1)

        files = tf.data.Dataset.list_files(
            '{}/*tfrecord*'.format(dataset_dir))
        dataset = files.interleave(
            tf.data.TFRecordDataset,
            np.maximum(np.minimum(len(image_path_list)//10,50),1)
        )
        if mode == 'train':
            dataset = dataset.repeat()
            dataset = dataset.shuffle(len(image_path_list))
        dataset = dataset.map(parse_example)
        if truth_only == True:
            dataset = dataset.filter(predicate)
        dataset = dataset.batch(batch_size)
        if mode == 'train':
            dataset = dataset.shuffle(buffer_size=500)
        iterator = dataset.make_one_shot_iterator()

        next_element = iterator.get_next()
        if 'test' in mode:
            next_element = [next_element[0],next_element[1]]

    elif np.all([extension == 'h5',
                 dataset_dir != None,
                 mode in ['train','test']]):
        key_list = [x.strip() for x in open(args.key_list).readlines()]
        next_element = tf_dataset_from_generator(
            generator=generate_images_h5py_dataset,
            generator_params={
                'h5py_path':hdf5_path,
                'input_height':input_height,
                'input_width':input_width,
                'key_list':key_list
                },
            output_types=output_types,
            output_shapes=output_shapes,
            is_training=is_training,
            buffer_size=500,
            batch_size=batch_size)
        image_path_list = key_list
    else:
        if 'tumble' in mode:
            gen_mode = mode.replace('tumble_','')
        else:
            gen_mode = mode

        next_element = tf_dataset_from_generator(
            generator=generate_images,
            generator_params={
                'image_path_list':image_path_list,
                'truth_path':truth_dir,
                'input_height':input_height,
                'input_width':input_width,
                'n_classes':n_classes,
                'truth_only':truth_only,
                'mode':gen_mode
                },
            output_types=output_types,
            output_shapes=output_shapes,
            is_training=is_training,
            buffer_size=500,
            batch_size=batch_size)

    if epochs != None:
        number_of_steps = epochs * int(len(image_path_list)/batch_size)

    if mode == 'train':
        inputs,truth,weights = next_element
        IA = tf_da.ImageAugmenter(**data_augmentation_params)
        inputs_original = inputs
        inputs,truth,weights = tf.map_fn(
            lambda x: IA.augment(x[0],x[1],x[2]),
            [inputs,truth,weights],
            (tf.float32,tf.float32,tf.float32)
            )

    elif 'test' in mode:
        inputs,truth = next_element
        truth = tf.cast(truth,tf.float32)
        weights = tf.placeholder(tf.float32,
                                 [batch_size,input_height,input_width,1])

    elif 'predict' in mode:
        inputs,image_names = next_element
        truth = tf.placeholder(tf.float32,
                               [batch_size,input_height,input_width,n_classes])
        weights = tf.placeholder(tf.float32,
                                 [batch_size,input_height,input_width,1])

    elif mode == 'large_predict':
        inputs,large_image_path,large_image_coords,batch_shape = next_element
        truth = tf.placeholder(tf.float32,
                               [batch_size,input_height,input_width,n_classes])
        weights = tf.placeholder(tf.float32,
                                 [batch_size,input_height,input_width,1])

    if 'tumble' in mode:
        flipped_inputs = tf.image.flip_left_right(inputs)
        inputs = tf.concat(
            [inputs,
             tf.image.rot90(inputs,1),
             tf.image.rot90(inputs,2),
             tf.image.rot90(inputs,3),
             flipped_inputs,
             tf.image.rot90(flipped_inputs,1),
             tf.image.rot90(flipped_inputs,2),
             tf.image.rot90(flipped_inputs,3)],
            axis=0
            )

    inputs = tf.image.convert_image_dtype(inputs,tf.float32)

    if padding == 'VALID':
        net_x,net_y = input_height - 184,input_width - 184
        tf_shape = [None,net_x,net_y,n_classes]
        if is_training == True:
            truth = truth[:,92:(input_height - 92),92:(input_width - 92),:]
            weights = weights[:,92:(input_height - 92),92:(input_width - 92),:]
        crop = True

    else:
        if resize == True:
            inputs = tf.image.resize_bilinear(images,
                                              [resize_height,resize_width])
            if is_training == True:
                truth = tf.image.resize_bilinear(
                    truth,
                    [resize_height,resize_width])
                weights = tf.image.resize_bilinear(
                    weights,
                    [resize_height,resize_width])
        net_x,net_y = (None, None)
        crop = False

    weights = tf.squeeze(weights,axis=-1)

    network,endpoints,classifications = u_net(
        inputs,
        final_endpoint=None,
        padding=padding,
        factorization=factorization,
        residuals=residuals,
        beta=beta_l2_regularization,
        n_classes=n_classes,
        depth_mult=depth_mult,
        aux_node=aux_node,
        squeeze_and_excite=squeeze_and_excite
        )

    log_write_print(log_file,
                    'Total parameters: {0:d} (trainable: {1:d})\n'.format(
                        variables(tf.all_variables()),
                        variables(tf.trainable_variables())
                        ))

    saver = tf.train.Saver()
    loading_saver = tf.train.Saver()

    class_balancing = tf.stack(
        [tf.ones_like(truth[:,:,:,i])/(tf.reduce_sum(truth[:,:,:,i])+1)
         for i in range(n_classes)],
        axis=3
        )

    class_balancing = tf.where(class_balancing < 0.001,
                               tf.ones_like(class_balancing) * 0.001,
                               class_balancing)

    if iglovikov == True:
        loss = iglovikov_loss(truth,network)

    else:
        loss = tf.nn.sigmoid_cross_entropy_with_logits(
            logits=network,labels=truth)
        loss = tf.reduce_sum(loss,axis=-1)
        loss = loss * weights
        loss = tf.reduce_mean(loss,axis=[1,2])

    if acl != 0:
        loss += acl*active_contour_loss(truth,tf.nn.softmax(network,axis=-1))

    loss = tf.reduce_mean(loss)

    if beta_l2_regularization > 0:
        reg_losses = slim.losses.get_regularization_losses()
        loss = loss + tf.add_n(reg_losses) / len(reg_losses)

    prediction_network = network

    if 'tumble' in mode:
        flipped_prediction = tf.image.flip_left_right(
            network[4:,:,:,:])
        network = network[:4,:,:,:]

        pred_list = [
            network[0,:,:,:],
            tf.image.rot90(network[1,:,:,:],-1),
            tf.image.rot90(network[2,:,:,:],-2),
            tf.image.rot90(network[3,:,:,:],-3),
            flipped_prediction[0,:,:,:],
            tf.image.rot90(flipped_prediction[1,:,:,:],1),
            tf.image.rot90(flipped_prediction[2,:,:,:],-2),
            tf.image.rot90(flipped_prediction[3,:,:,:],-1)]

        network = tf.stack(pred_list,axis=0)
        prediction_network = tf.reduce_mean(network,
                                            axis=0,
                                            keepdims=True)

    if n_classes == 2:
        binarized_network = tf.argmax(prediction_network,axis=-1)
        binarized_truth = tf.argmax(truth,axis=-1)
    elif n_classes == 3:
        binarized_network = tf.cast(tf.argmax(prediction_network,axis=-1),
                                    tf.float32)
        binarized_network = tf.where(prediction_network[:,:,:,2] > prediction_network[:,:,:,1],
                                     tf.zeros_like(binarized_network),
                                     binarized_network)
        binarized_truth = tf.cast(tf.argmax(truth,axis=-1),
                                  tf.float32)
        binarized_truth = tf.where(truth[:,:,:,2] == 1,
                                   tf.zeros_like(binarized_truth),
                                   binarized_truth)

    batch_vars = [v for v in tf.local_variables()]
    batch_vars = [v for v in batch_vars if 'batch' in v.name]
    #train_op = tf.train.MomentumOptimizer(learning_rate,0.99).minimize(loss)
    global_step = tf.train.get_or_create_global_step()
    learning_rate = tf.train.cosine_decay(
        learning_rate=learning_rate,
        global_step=global_step,
        decay_steps=int(number_of_steps * 0.8)
    )
    optimizer = tf.train.AdamOptimizer(learning_rate)

    update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    with tf.control_dependencies(update_ops):
        train_op = optimizer.minimize(loss,global_step=global_step)

    if aux_node:
        presence = tf.reduce_sum(binarized_truth,axis=[1,2]) > 0
        presence = tf.expand_dims(
            tf.cast(presence,tf.float32),
            axis=1)
        class_loss = tf.reduce_mean(
            tf.add_n(
                [
                    tf.nn.sigmoid_cross_entropy_with_logits(
                        labels=presence,
                        logits=c) for c in classifications
                ]
            )
        )
        trainable_variables = tf.trainable_variables()
        aux_vars = []
        for var in trainable_variables:
            if 'Aux_Node' in var.name:
                aux_vars.append(var)
        aux_optimizer = tf.train.AdamOptimizer(learning_rate)
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        with tf.control_dependencies(update_ops):
            class_train_op = aux_optimizer.minimize(
                    class_loss,
                    var_list=aux_vars,
                    global_step=global_step
                )
        train_op = tf.group(train_op,class_train_op)
        loss = [loss,class_loss]

    if 'train' in mode or 'test' in mode:
        if n_classes == 2:
            prediction_summary = tf.expand_dims(tf.nn.softmax(
                prediction_network,axis = -1)[:,:,:,1],-1)
            prediction_binary_summary = tf.expand_dims(binarized_network,axis=-1)
            binarized_truth_summary = tf.expand_dims(binarized_truth,axis=-1)
            probs_summary = prediction_summary

        else:
            prediction_summary = tf.nn.softmax(prediction_network,axis=-1)
            prediction_binary_summary = tf.expand_dims(binarized_network,axis=-1)
            binarized_truth_summary = tf.expand_dims(binarized_truth,axis=-1)
            max_bool = tf.equal(
                tf.reduce_max(prediction_network,axis=-1,keepdims=True),
                prediction_network
            )
            probs_summary = tf.reduce_max(
                tf.multiply(
                    tf.cast(max_bool,tf.float32),
                    tf.stack([1 - prediction_summary[:,:,:,0],
                              prediction_summary[:,:,:,1],
                              1 - prediction_summary[:,:,:,2]],
                              axis=-1)
                ),
                axis=-1
            )

        auc, auc_op = tf.metrics.auc(
            binarized_truth,
            probs_summary,
            num_thresholds=50)
        f1score,f1score_op = tf.contrib.metrics.f1_score(
            binarized_truth,
            binarized_network)
        m_iou,m_iou_op = tf.metrics.mean_iou(
            labels=binarized_truth,
            predictions=binarized_network,
            num_classes=2)
        auc_batch, auc_batch_op = tf.metrics.auc(
            binarized_truth,
            probs_summary,
            name='auc_batch',
            num_thresholds=50)
        f1score_batch,f1score_batch_op = tf.contrib.metrics.f1_score(
            binarized_truth,
            binarized_network,
            name='f1_batch')
        m_iou_batch,m_iou_batch_op = tf.metrics.mean_iou(
            labels=binarized_truth,
            predictions=binarized_network,
            num_classes=2,
            name='m_iou_batch')

        summaries = set(tf.get_collection(tf.GraphKeys.SUMMARIES))

        if 'train' in mode:
            for endpoint in endpoints:
                x = endpoints[endpoint]
                summaries.add(tf.summary.histogram('activations/' + endpoint, x))

            for variable in slim.get_model_variables():
                summaries.add(tf.summary.histogram(variable.op.name, variable))

            if aux_node:
                summaries.add(tf.summary.scalar('loss', loss[0]))
                summaries.add(tf.summary.scalar('class_loss', class_loss))
            else:
                summaries.add(tf.summary.scalar('loss', loss))

            summaries.add(tf.summary.scalar('f1score', f1score))
            summaries.add(tf.summary.scalar('auc', auc))
            summaries.add(tf.summary.scalar('mean_iou',m_iou))

            summaries.add(
                tf.summary.image('image_original',inputs_original,max_outputs = 4))
            summaries.add(
                tf.summary.image('image_transformed',inputs,max_outputs = 4))
            summaries.add(
                tf.summary.image('truth_image',
                                 tf.cast(
                                     binarized_truth_summary,tf.float32),
                                 max_outputs = 4))
            summaries.add(
                tf.summary.image('weight_map',
                                 tf.expand_dims(weights,-1),
                                 max_outputs = 4))

            if n_classes > 2:
                for i in range(n_classes):
                    summaries.add(
                        tf.summary.image(
                            'prediction_channel_{}'.format(i),
                            tf.expand_dims(prediction_summary[:,:,:,i],axis=-1),
                            max_outputs = 4))
                    summaries.add(
                        tf.summary.image(
                            'truth_channel_{}'.format(i),
                            tf.expand_dims(truth[:,:,:,i],axis=-1),
                            max_outputs = 4))
            else:
                summaries.add(
                    tf.summary.image(
                        'prediction_channel_0',
                        prediction_summary,
                        max_outputs = 4))
                summaries.add(
                    tf.summary.image(
                        'truth_channel_0',
                        tf.expand_dims(truth[:,:,:,1],axis=-1),
                        max_outputs = 4))

            summaries.add(
                tf.summary.image('prediction_binary',
                                 tf.cast(
                                     prediction_binary_summary,tf.float32),
                                 max_outputs = 4))

            summary_op = tf.summary.merge(list(summaries), name='summary_op')

    init = tf.group(
        tf.global_variables_initializer(),
        tf.local_variables_initializer(),
        tf.tables_initializer()
        )

    tf.set_random_seed(0)
    np.random.seed(42)

    ckpt_exists = os.path.exists(checkpoint_path + '.index')
    if len(image_path_list) > 0:

        if mode == 'train':

            print("Training the network...\n")
            LOG = 'Step {0:d}: minibatch loss: {1:f}. '
            LOG += 'Average time/minibatch = {2:f}s. '
            LOG += 'F1-Score: {3:f}; AUC: {4:f}; MeanIOU: {5:f}'
            SUMMARY = 'Step {0:d}: summary stored in {1!s}'
            CHECKPOINT = 'Step {0:d}: checkpoint stored in {1!s}'
            CHECKPOINT_PATH = os.path.join(save_checkpoint_folder,
                                           'my_u-net.ckpt')

            try:
                os.makedirs(save_checkpoint_folder)
            except:
                pass

            try:
                os.makedirs(save_summary_folder)
            except:
                pass

            config = tf.ConfigProto()

            local_dev = device_lib.list_local_devices()
            n_gpu = len([x.name for x in local_dev if x.device_type == 'GPU'])

            if n_gpu > 0:
                config.gpu_options.polling_inactive_delay_msecs = 2000
                config.gpu_options.allow_growth = True
            else:
                n_phys_cores = psutil.cpu_count(logical = False)
                config.intra_op_parallelism_threads = n_phys_cores
                config.inter_op_parallelism_threads = n_phys_cores

            with tf.Session(config = config) as sess:
                writer = tf.summary.FileWriter(save_summary_folder,sess.graph)

                sess.run(init)

                if ckpt_exists:
                    loading_saver.restore(sess,checkpoint_path)
                    print('Restored')

                time_list = []

                all_class_losses = []
                for i in range(number_of_steps):
                    a = time.perf_counter()
                    _,l,_,_,_ = sess.run(
                        [train_op,loss,f1score_op,auc_op,m_iou_op])

                    if aux_node:
                        class_l = l[1]
                        l = l[0]
                        all_class_losses.append(class_l)
                    b = time.perf_counter()
                    time_list.append(b - a)
                    if i % log_every_n_steps == 0 or i == 1:
                        l,_ = sess.run([loss,(auc_op,f1score_op,m_iou_op)])
                        f1,auc_,miou = sess.run([f1score,auc,m_iou])
                        log_write_print(log_file,
                                        LOG.format(i,l,np.mean(time_list),
                                                   f1,auc_,miou))
                        time_list = []
                        if aux_node:
                            class_l = np.mean(all_class_losses)
                            all_class_losses = []
                            print('\tAux_Node loss = {}'.format(class_l))

                    if i % save_summary_steps == 0 or i == 1:
                        summary = sess.run(summary_op)
                        writer.add_summary(summary,i)
                        log_write_print(
                            log_file,SUMMARY.format(i,save_summary_folder))

                        if i % save_checkpoint_steps == 0 or i == 1:
                            saver.save(sess, CHECKPOINT_PATH,global_step=i)
                            log_write_print(log_file,
                                            CHECKPOINT.format(i,
                                                              CHECKPOINT_PATH))
                        sess.run(tf.local_variables_initializer())

                summary = sess.run(summary_op)
                writer.add_summary(summary,i)
                log_write_print(
                    log_file,SUMMARY.format(i,save_summary_folder))
                saver.save(sess,CHECKPOINT_PATH,global_step=i)
                log_write_print(log_file,
                                CHECKPOINT.format(i,CHECKPOINT_PATH))

        elif 'test' in mode and ckpt_exists:
            LOG = 'Time/{0:d} images: {1:f}s (time/1 image: {2:f}s). '
            LOG += 'F1-Score: {3:f}; AUC: {4:f}; MeanIOU: {5:f}'

            FINAL_LOG = 'Final averages - time/image: {0}s; F1-score: {1}; '
            FINAL_LOG += 'AUC: {2}; MeanIOU: {3}'

            print('Testing...')

            prob_net = tf.nn.softmax(prediction_network,axis=-1)

            with tf.Session() as sess:

                sess.run(init)
                trained_network = saver.restore(sess,checkpoint_path)

                keep_going = True

                all_probs = []
                all_true = []
                time_list = []

                while keep_going == True:

                    try:
                        a = time.perf_counter()
                        img,truth = sess.run(
                            [prob_net,binarized_truth])

                        probabilities = img[:,:,:,1].flatten()

                        all_probs.append(probabilities)
                        all_true.append(truth.flatten())

                        n_images = img.shape[0]
                        b = time.perf_counter()
                        t_image = (b - a)/n_images
                        time_list.append(t_image)

                    except:
                        keep_going = False

                iou_list = [metrics.jaccard_score(a,b>=0.5)
                            for a,b in zip(all_true,all_probs)
                            if len(np.unique(a)) == 2]
                auc_list = [metrics.roc_auc_score(a,b)
                            for a,b in zip(all_true,all_probs)
                            if len(np.unique(a)) == 2]
                f1s_list = [metrics.f1_score(a,b>=0.5)
                            for a,b in zip(all_true,all_probs)
                            if len(np.unique(a)) == 2]

                all_probs = np.array(all_probs).flatten()
                all_true = np.array(all_true).flatten()

                iou = metrics.jaccard_score(all_true,all_probs >= 0.5)
                auc = metrics.roc_auc_score(all_true,all_probs >= 0.5)
                f1s = metrics.f1_score(all_true,all_probs >= 0.5)

                output = "TEST,IOU,global,{}\n".format(iou)
                output += "TEST,AUC,global,{}\n".format(auc)
                output += "TEST,F1-score,global,{}\n".format(f1s)

                for metric,metric_name in [
                    [iou_list,'IOU'],[auc_list,'AUC'],[f1s_list,'F1-score'],
                    [time_list,"time"]]:
                    output += "TEST,{},mean,{}\n".format(
                        metric_name,np.mean(metric))
                    output += "TEST,{},sd,{}\n".format(
                        metric_name,np.std(metric))
                    output += "TEST,{},q05,{}\n".format(
                        metric_name,np.quantile(metric,0.05))
                    output += "TEST,{},q95,{}\n".format(
                        metric_name,np.quantile(metric,0.95))

                log_write_print(log_file,output)

        elif 'predict' in mode and ckpt_exists:
            print('Predicting...')

            LOG = 'Time/{0:d} images: {1:f}s (time/1 image: {2:f}s).'
            FINAL_LOG = 'Average time/image: {0:f}'

            prob_network = tf.nn.softmax(network)[:,:,:,1]

            with tf.Session() as sess:
                try:
                    os.makedirs(prediction_output)
                except:
                    pass

                sess.run(init)
                trained_network = saver.restore(sess,checkpoint_path)

                time_list = []

                keep_going = True

                while keep_going == True:

                    try:
                        a = time.perf_counter()
                        prediction,im_names = sess.run([prediction_network,
                                                        image_names])
                        n_images = prediction.shape[0]
                        b = time.perf_counter()
                        t_image = (b - a)/n_images
                        time_list.append(t_image)

                        output = LOG.format(n_images,b - a,t_image)
                        log_write_print(log_file,output)

                        for i in range(prediction.shape[0]):
                            image = prediction[i,:,:]
                            image_name = im_names[i].decode().split(os.sep)[-1]
                            image_name = '.'.join(image_name.split('.')[:-1])
                            image_name = image_name + '.tif'
                            image_output = os.path.join(prediction_output,
                                                        image_name)
                            tiff.imsave(image_output,image)

                    except:
                        keep_going = False

                avg_time = np.mean(time_list)
                output = FINAL_LOG.format(avg_time)
                log_write_print(log_file,output)

        elif mode == 'large_predict' and ckpt_exists:
            print('Predicting large image...')

            LOG = 'Time/{0:d} images: {1:f}s (time/1 image: {2:f}s).'
            FINAL_LOG = 'Average time/image: {0:f}.\nTotal stats: {1:f}s '
            FINAL_LOG += 'for {2:d} images.'
            start = time.perf_counter()
            with tf.Session() as sess:

                try:
                    os.makedirs(large_prediction_output)
                except:
                    pass

                if prediction_output != 'no_path':
                    try:
                        os.makedirs(prediction_output)
                    except:
                        pass

                sess.run(init)
                trained_network = saver.restore(sess,checkpoint_path)

                time_list = []

                curr_image_name = ''

                for batch,image_names,coords,shapes in image_generator:
                    n_images = len(batch)
                    batch = np.stack(batch,0)

                    a = time.perf_counter()
                    prediction = sess.run(network)
                    b = time.perf_counter()
                    t_image = (b - a)/n_images
                    time_list.append(t_image)

                    output = LOG.format(n_images,b - a,t_image)
                    log_write_print(log_file,output)

                    for i in range(prediction.shape[0]):
                        image_name = image_names[i].split(os.sep)[-1]
                        if image_name != curr_image_name:
                            if curr_image_name != '':
                                division_mask[division_mask == 0] = 1
                                image = np.argmax(mask/division_mask,axis = 2)
                                image = np.stack((image,image,image),axis = 2)
                                image = image.astype('uint8')
                                image = Image.fromarray(image)
                                image.save(large_image_output_name)
                            curr_image_name = image_name
                            final_height,final_width = shapes[i][0:2]
                            if padding == 'VALID':
                                final_height = final_height - 184
                                final_width = final_width - 184
                            mask = np.zeros(
                                (final_height,final_width,n_classes)
                            )
                            division_mask = np.zeros(
                                (final_height,final_width,n_classes)
                            )
                            large_image_output_name = os.path.join(
                                large_prediction_output,
                                curr_image_name
                                )
                        h_1,w_1 = coords[i]
                        tile = prediction[i,:,:]
                        remap_tiles(mask,division_mask,h_1,w_1,tile)

                    division_mask[division_mask == 0] = 1
                    image = np.argmax(mask/division_mask,axis = 2)
                    image[image >= 0.5] = 1
                    image[image < 0.5] = 0
                    image = np.stack((image,image,image),axis = 2)
                    image = image.astype('uint8')
                    image = Image.fromarray(image)
                    image.save(large_image_output_name)

                finish = time.perf_counter()
                avg_time = np.mean(time_list)
                output = FINAL_LOG.format(avg_time,finish - start,
                                          len(image_path_list))
                log_write_print(log_file,output)

#Defining arguments

parser = argparse.ArgumentParser(
    prog = 'u-net.py',
    description = 'Multi-purpose U-Net implementation.'
)

parser.add_argument('--mode',dest = 'mode',
                    action = 'store',
                    default = 'train',
                    help = 'Algorithm mode.')

#Logs
parser.add_argument('--log_file',dest = 'log_file',
                    action = ToDirectory,type = str,
                    default = os.getcwd() + '/log.txt',
                    help = 'Directory where training logs are written.')
parser.add_argument('--log_every_n_steps',dest = 'log_every_n_steps',
                    action = 'store',type = int,
                    default = 100,
                    help = 'How often are the loss and global step logged.')

#Summaries
parser.add_argument('--save_summary_steps',dest = 'save_summary_steps',
                    action = 'store',type = int,
                    default = 100,
                    metavar = '',
                    help = 'How often summaries are saved.')
parser.add_argument('--save_summary_folder',dest = 'save_summary_folder',
                    action = ToDirectory,type = str,
                    default = os.getcwd(),
                    help = 'Directory where summaries are saved.')

#Checkpoints
parser.add_argument('--save_checkpoint_steps',dest = 'save_checkpoint_steps',
                    action = 'store',type = int,
                    default = 100,
                    help = 'How often checkpoints are saved.')
parser.add_argument('--save_checkpoint_folder',dest = 'save_checkpoint_folder',
                    action = ToDirectory,type = str,
                    default = os.getcwd(),
                    metavar = '',
                    help = 'Directory where checkpoints are saved.')

#Training
parser.add_argument('--squeeze_and_excite',dest='squeeze_and_excite',
                    action='store_true',
                    default=False,
                    help='Adds SC SqAndEx layers to the enc/dec.')
parser.add_argument('--iglovikov',dest='iglovikov',
                    action = 'store_true',
                    default = False,
                    help = 'Use Iglovikov loss function.')
parser.add_argument('--batch_size',dest = 'batch_size',
                    action = 'store',type = int,
                    default = 100,
                    help = 'Size of mini batch.')
parser.add_argument('--number_of_steps',dest = 'number_of_steps',
                    action = 'store',type = int,
                    default = 5000,
                    help = 'Number of steps in the training process.')
parser.add_argument('--epochs',dest = 'epochs',
                    action = 'store',type = int,
                    default = None,
                    help = 'Number of epochs (overrides number_of_steps).')
parser.add_argument('--acl',dest = 'acl',
                    action = 'store',type = float,
                    default = 0.,
                    help = 'Multiplier for the active contour loss.')
parser.add_argument('--beta_l2_regularization',dest = 'beta_l2_regularization',
                    action = 'store',type = float,
                    default = 0,
                    help = 'Beta parameter for L2 regularization.')
parser.add_argument('--learning_rate',dest = 'learning_rate',
                    action = 'store',type = float,
                    default = 0.001,
                    help = 'Learning rate for the SGD optimizer.')
parser.add_argument('--factorization',dest = 'factorization',
                    action = 'store_true',
                    default = False,
                    help = 'Use convolutional layer factorization.')
parser.add_argument('--residuals',dest = 'residuals',
                    action = 'store_true',
                    default = False,
                    help = 'Use residuals in skip connections.')
parser.add_argument('--weighted',dest = 'weighted',
                    action = 'store_true',
                    default = False,
                    help = 'Calculates weighted cross entropy.')
parser.add_argument('--depth_mult',dest = 'depth_mult',
                    action = 'store',type = float,
                    default = 1.,
                    help = 'Change the number of channels in all layers.')
parser.add_argument('--truth_only',dest = 'truth_only',
                    action = 'store_true',
                    default = False,
                    help = 'Consider only images with all classes.')
parser.add_argument('--aux_node',dest = 'aux_node',
                    action = 'store_true',
                    default = False,
                    help = 'Aux node for classification task in bottleneck.')

parser.add_argument('--checkpoint_path',dest = 'checkpoint_path',
                    action = ToDirectory,
                    default = 'no_path',
                    help = 'Path to checkpoint to restore.')

#Prediction
parser.add_argument('--prediction_output',dest = 'prediction_output',
                    action = ToDirectory,
                    default = 'no_path',
                    help = 'Path where image predictions are stored.')

#Large image prediction
parser.add_argument('--large_prediction_output',
                    dest = 'large_prediction_output',
                    action = ToDirectory,
                    default = 'no_path',
                    help = 'Path to store large image predictions.')

#Data augmentation
for arg in [
    ['brightness_max_delta',16. / 255.,float],
    ['saturation_lower',0.8,float],
    ['saturation_upper',1.2,float],
    ['hue_max_delta',0.2,float],
    ['contrast_lower',0.8,float],
    ['contrast_upper',1.2,float],
    ['salt_prob',0.1,float],
    ['pepper_prob',0.1,float],
    ['noise_stddev',0.05,float],
    ['blur_probability',0.1,float],
    ['blur_size',3,int],
    ['blur_mean',0,float],
    ['blur_std',0.05,float],
    ['discrete_rotation',True,'store_true'],
    ['min_jpeg_quality',30,int],
    ['max_jpeg_quality',70,int],
    ['elastic_transform_p',0.3,float]
]:
    print(arg[0])
    if arg[2] != 'store_true':
        parser.add_argument('--{}'.format(arg[0]),dest=arg[0],
                            action='store',type=arg[2],
                            default=arg[1])
    else:
        parser.add_argument('--{}'.format(arg[0]),dest=arg[0],
                            action='store_true',
                            default=False)
#Pre-processing
parser.add_argument('--noise_chance',dest = 'noise_chance',
                    action = 'store',type = float,
                    default = 0.1,
                    help = 'Probability to add noise.')
parser.add_argument('--blur_chance',dest = 'blur_chance',
                    action = 'store',type = float,
                    default = 0.05,
                    help = 'Probability to blur the input image.')
parser.add_argument('--resize',dest = 'resize',
                    action = 'store_true',
                    default = False,
                    help = 'Resize images to input_height and input_width.')
parser.add_argument('--resize_height',dest = 'resize_height',
                    action = 'store',
                    default = 256,
                    help = 'Height for resized images.')
parser.add_argument('--resize_width',dest = 'resize_width',
                    action = 'store',
                    default = 256,
                    help = 'Height for resized images.')

#Dataset
parser.add_argument('--dataset_dir',dest = 'dataset_dir',
                    action = ToDirectory,
                    default = None,
                    type = str,
                    help = 'Directory where the training set is stored.')
parser.add_argument('--path_csv',dest = 'path_csv',
                    action = ToDirectory,
                    default = None,
                    type = str,
                    help = 'CSV with QCd paths.')
parser.add_argument('--truth_dir',dest = 'truth_dir',
                    action = ToDirectory,type = str,
                    help = 'Path to segmented images.')
parser.add_argument('--padding',dest = 'padding',
                    action = 'store',
                    default = 'VALID',
                    help = 'Define padding.',
                    choices = ['VALID','SAME'])
parser.add_argument('--extension',dest = 'extension',
                    action = 'store',type = str,
                    default = '.png',
                    help = 'The file extension for all images.')
parser.add_argument('--input_height',dest = 'input_height',
                    action = 'store',type = int,
                    default = 256,
                    help = 'The file extension for all images.')
parser.add_argument('--input_width',dest = 'input_width',
                    action = 'store',type = int,
                    default = 256,
                    help = 'The file extension for all images.')
parser.add_argument('--n_classes',dest = 'n_classes',
                    action = 'store',type = int,
                    default = 2,
                    help = 'Number of classes in the segmented images.')
parser.add_argument('--trial',dest = 'trial',
                    action = 'store_true',
                    default = False,
                    help = 'Subsamples the dataset for a quick run.')
parser.add_argument('--key_list',dest = 'key_list',
                    action = 'store',
                    default = None,
                    help = 'File with one image file per list (for h5 \
                    extension).')

args = parser.parse_args()

mode = args.mode

#Logs
log_file = args.log_file
log_every_n_steps = args.log_every_n_steps

#Summaries
save_summary_steps = args.save_summary_steps
save_summary_folder = args.save_summary_folder

#Checkpoints
save_checkpoint_steps = args.save_checkpoint_steps
save_checkpoint_folder = args.save_checkpoint_folder
checkpoint_path = args.checkpoint_path

#Training
squeeze_and_excite = args.squeeze_and_excite
iglovikov = args.iglovikov
batch_size = args.batch_size
number_of_steps = args.number_of_steps
epochs = args.epochs
acl = args.acl
beta_l2_regularization = args.beta_l2_regularization
learning_rate = args.learning_rate
factorization = args.factorization
residuals = args.residuals
weighted = args.weighted
depth_mult = args.depth_mult
truth_only = args.truth_only
aux_node = args.aux_node

#Prediction
prediction_output = args.prediction_output

#Large image prediction
large_prediction_output = args.large_prediction_output

#Data augmentation
data_augmentation_params = {
    'brightness_max_delta':args.brightness_max_delta,
    'saturation_lower':args.saturation_lower,
    'saturation_upper':args.saturation_upper,
    'hue_max_delta':args.hue_max_delta,
    'contrast_lower':args.contrast_lower,
    'contrast_upper':args.contrast_upper,
    'salt_prob':args.salt_prob,
    'pepper_prob':args.pepper_prob,
    'noise_stddev':args.noise_stddev,
    'blur_probability':args.blur_probability,
    'blur_size':args.blur_size,
    'blur_mean':args.blur_mean,
    'blur_std':args.blur_std,
    'discrete_rotation':args.discrete_rotation,
    'min_jpeg_quality':args.min_jpeg_quality,
    'max_jpeg_quality':args.max_jpeg_quality,
    'elastic_transform_p':args.elastic_transform_p
}

#Pre-processing
resize = args.resize
resize_height = args.resize_height
resize_width = args.resize_width

#Dataset
dataset_dir = args.dataset_dir
path_csv = args.path_csv
truth_dir = args.truth_dir
padding = args.padding
extension = args.extension
input_height = args.input_height
input_width = args.input_width
n_classes = args.n_classes
trial = args.trial

if __name__ == '__main__':
    print("Loading dependencies...")

    import sys
    import time
    from glob import glob
    from math import floor,inf
    import numpy as np
    import cv2
    import tensorflow as tf
    import psutil
    from tensorflow.python.client import device_lib
    from PIL import Image
    from scipy.spatial import distance

    tf.logging.set_verbosity(tf.logging.ERROR)
    slim = tf.contrib.slim
    variance_scaling_initializer =\
     tf.contrib.layers.variance_scaling_initializer

    main(log_file=log_file,
         log_every_n_steps=log_every_n_steps,
         save_summary_steps=save_summary_steps,
         save_summary_folder=save_summary_folder,
         save_checkpoint_steps=save_checkpoint_steps,
         save_checkpoint_folder=save_checkpoint_folder,
         squeeze_and_excite=squeeze_and_excite,
         iglovikov=iglovikov,
         batch_size=batch_size,
         number_of_steps=number_of_steps,
         epochs=epochs,
         acl=acl,
         beta_l2_regularization=beta_l2_regularization,
         learning_rate=learning_rate,
         factorization=factorization,
         residuals=residuals,
         weighted=weighted,
         depth_mult=depth_mult,
         truth_only=truth_only,
         mode=mode,
         checkpoint_path=checkpoint_path,
         prediction_output=prediction_output,
         large_prediction_output=large_prediction_output,
         data_augmentation_params=data_augmentation_params,
         dataset_dir=dataset_dir,
         path_csv=path_csv,
         truth_dir=truth_dir,
         padding=padding,
         extension=extension,
         input_height=input_height,
         input_width=input_width,
         n_classes=n_classes,
         trial=trial,
         aux_node=aux_node)
