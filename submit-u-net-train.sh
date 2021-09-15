EPOCHS=30000
TRAIN_SET_FILES=training_set_files

submit_unet() {
  if [ ! -d $3 ]
  then
    bsub\
      -P gpu\
      -M 16000\
      -g /salim_gpu\
      -gpu "num=1:j_exclusive=yes"\
      -q research-rh74\
      -m "gpu-009 gpu-011"\
      -J unet_$(basename $4)_$1\
      -o logs/$(basename $2).o\
      -e logs/$(basename $2).e\
      sh train-u-net-hdf5.sh\
      $@
  fi
}

submit_unet_na() {
  if [ ! -d $3 ]
  then
    bsub\
      -P gpu\
      -M 16000\
      -g /salim_gpu\
      -gpu "num=1:j_exclusive=yes"\
      -q research-rh74\
      -m "gpu-009 gpu-011"\
      -J unet_$(basename $4)_$1\
      -o logs/$(basename $2).o\
      -e logs/$(basename $2).e\
      sh train-u-net-hdf5-no-aug.sh\
      $@
  fi
}

for depth in 0.1 0.25 0.5 1.0
do
  if [ $depth == 1.0 ]
  then
    epochs=$((2 * $EPOCHS))
  else
    epochs=$EPOCHS
  fi

  for dataset in /hps/research/gerstung/josegcpa/projects/01IMAGE/u-net/segmentation_dataset /hps/research/gerstung/josegcpa/projects/01IMAGE/u-net/segmentation_dataset_munich
  do
    iden=$(basename $dataset)_$depth

    submit_unet $depth summaries/$iden checkpoints/$iden "$dataset".h5 $epochs $TRAIN_SET_FILES
    submit_unet $depth summaries/sae_$iden checkpoints/sae_$iden "$dataset".h5 $epochs $TRAIN_SET_FILES "--squeeze_and_excite"
    submit_unet_na $depth summaries/"$iden"_transformed checkpoints/"$iden"_transformed "$dataset"_transformed.h5 $epochs $TRAIN_SET_FILES
    submit_unet_na $depth summaries/sae_"$iden"_transformed checkpoints/sae_"$iden"_transformed "$dataset"_transformed.h5 $epochs $TRAIN_SET_FILES "--squeeze_and_excite"

  done
done
