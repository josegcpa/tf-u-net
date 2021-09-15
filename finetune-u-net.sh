DEPTH=$1
SUMMARY_FOLDER=$2
CKPT_FOLDER=$3
DATASET_DIR=$4
NUMBER_OF_STEPS=$5
GEN_PATH=$6
KEY_LIST=$7
ADDITIONAL_ARGUMENTS=$8
CKPT_PATH=$(cat $GEN_PATH/checkpoint | tail -1 | cut -d ' ' -f 2 | awk '{gsub(/"/,""); print $0}')

source /hps/nobackup/research/gerstung/josegcpa/virtual_envs/tf_gpu_cuda9/bin/activate

echo $@

python3 u-net.py\
  --mode train\
  --log_every_n_steps 100\
  --save_summary_steps 100\
  --save_summary_folder $SUMMARY_FOLDER\
  --save_checkpoint_steps 500\
  --save_checkpoint_folder $CKPT_FOLDER\
  --batch_size 3\
  --number_of_steps $NUMBER_OF_STEPS\
  --beta_l2_regularization 0.005\
  --learning_rate 0.00001\
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
  --discrete_rotation\
  --min_jpeg_quality 1\
  --max_jpeg_quality 1\
  --elastic_transform_p 0.3\
  --dataset_dir $DATASET_DIR\
  --extension h5\
  --n_classes 2\
  --padding SAME\
  --input_height 512\
  --input_width 512\
  --depth_mult $DEPTH\
  --key_list $KEY_LIST\
  --checkpoint_path $CKPT_PATH $ADDITIONAL_ARGUMENTS
