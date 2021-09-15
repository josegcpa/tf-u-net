source /hps/nobackup/research/gerstung/josegcpa/virtual_envs/tf_gpu_cuda9/bin/activate

DEPTH=$1
GEN_PATH=$2
MODE=$3
INPUT=$4
TRUTH=$5
EXTRA_ARG=$6
CKPT_PATH=$(cat $GEN_PATH/checkpoint | tail -1 | cut -d ' ' -f 2 | awk '{gsub(/"/,""); print $0}')

if [ $MODE == TUMBLE ]
then
  mode=tumble_test
else
  mode=test
fi

echo $mode

echo $@

TF_CUDNN_USE_AUTOTUNE=0
echo python3 u-net.py\
  --mode $mode\
  --checkpoint_path $CKPT_PATH\
  --log_every_n_steps 10\
  --batch_size 1\
  --dataset_dir $INPUT\
  --truth_dir $TRUTH\
  --n_classes 2\
  --padding SAME\
  --input_height 512\
  --input_width 512\
  --depth_mult $DEPTH $EXTRA_ARG
