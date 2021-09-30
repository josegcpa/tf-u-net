source /hps/nobackup/research/gerstung/josegcpa/virtual_envs/tf_gpu_cuda9/bin/activate
#source /hps/nobackup/research/gerstung/josegcpa/virtual_envs/tf_cpu_1_12/bin/activate

DEPTH=$1
GEN_PATH=$2
MODE=$3
INPUT=$4
TRUTH=$5
EXTRA_ARG=$6
CKPT_PATH=$(cat $GEN_PATH/checkpoint | tail -5 | head -1 | cut -d ' ' -f 2 | awk '{gsub(/"/,""); print $0}')

SIZE=512

if [ $MODE == TUMBLE ]
then
  mode=tumble_test
else
  mode=test
fi

echo $mode

echo $@

TF_CUDNN_USE_AUTOTUNE=0
python3 u-net.py\
  --mode $mode\
  --checkpoint_path $CKPT_PATH\
  --log_every_n_steps 10\
  --batch_size 1\
  --dataset_dir $INPUT\
  --truth_dir $TRUTH\
  --n_classes 2\
  --padding SAME\
  --input_height $SIZE\
  --input_width $SIZE\
  --depth_mult $DEPTH $EXTRA_ARG
