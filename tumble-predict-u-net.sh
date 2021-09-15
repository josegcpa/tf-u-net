source /hps/nobackup/research/gerstung/josegcpa/virtual_envs/tf_gpu_cuda9/bin/activate

DEPTH=$1
GEN_PATH=$2
CKPT_PATH=$(cat $GEN_PATH/checkpoint | tail -1 | cut -d ' ' -f 2 | awk '{gsub(/"/,""); print $0}')

TF_CUDNN_USE_AUTOTUNE=0
python3 u-net.py\
  --mode tumble_predict\
  --prediction_output /tmp/mimimimi\
  --checkpoint_path $CKPT_PATH\
  --log_every_n_steps 10\
  --batch_size 1\
  --dataset_dir full_split_512/test/input\
  --truth_dir full_split_512/test/truth\
  --n_classes 2\
  --padding SAME\
  --input_height 512\
  --input_width 512\
  --depth_mult $DEPTH
