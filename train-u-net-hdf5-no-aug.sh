DEPTH=$1
SUMMARY_FOLDER=$2
CKPT_FOLDER=$3
DATASET_DIR=$4
NUMBER_OF_STEPS=$5
KEY_LIST=$6
ADDITIONAL_ARGUMENTS=$7

source /hps/nobackup/research/gerstung/josegcpa/virtual_envs/tf_gpu_cuda9/bin/activate

python3 u-net.py\
  --mode train\
  --log_every_n_steps 1000\
  --save_summary_steps 1000\
  --save_checkpoint_steps 1000\
  --batch_size 4\
  --beta_l2_regularization 0.005\
  --learning_rate 0.001\
  --brightness_max_delta 0\
  --saturation_lower 1.0\
  --saturation_upper 1.0\
  --hue_max_delta 0\
  --contrast_lower 1.0\
  --contrast_upper 1.0\
  --salt_prob 0\
  --pepper_prob 0\
  --noise_stddev 0\
  --blur_probability 0\
  --blur_size 1\
  --blur_mean 0\
  --blur_std 0\
  --elastic_transform_p 0.3\
  --discrete_rotation\
  --min_jpeg_quality 1\
  --max_jpeg_quality 1\
  --n_classes 2\
  --padding SAME\
  --input_height 512\
  --input_width 512\
  --save_summary_folder $SUMMARY_FOLDER\
  --save_checkpoint_folder $CKPT_FOLDER\
  --dataset_dir $DATASET_DIR\
  --extension h5\
  --number_of_steps $NUMBER_OF_STEPS\
  --depth_mult $DEPTH\
  --key_list $KEY_LIST\
  $ADDITIONAL_ARGUMENTS
