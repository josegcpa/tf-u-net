echo TUMBLE,FINETUNE,TRANSFORMED,TRAIN_DATASET,TEST_DATASET,DEPTH,SAE,time,F1-score,AUC,MeanIOU
for output in test_output/*
do
    if [[ "$output" == *"TUMBLE"* ]]
    then
        TUMBLE=T
    else
        TUMBLE=F
    fi
    if [[ "$output" == *"FT"* ]]
    then
        FINETUNE=T
    else
        FINETUNE=F
    fi
    if [[ "$output" == *"transformed"* ]]
    then
        TRANSFORMED=T
    else
        TRANSFORMED=F
    fi
    if [[ "$output" == *"munich"* ]]
    then
        TRAIN_DATASET=MUNICH
    else
        TRAIN_DATASET=ADDENBROOKES
    fi
    if [[ "$output" == *"MUNICH"* ]]
    then
        TEST_DATASET=MUNICH
    else
        TEST_DATASET=ADDENBROOKES
    fi
    if [[ "$output" == *"sae"* ]]
    then
        SAE=T
    else
        SAE=F
    fi

    DEPTH=$(echo $output | grep -Eo [0-9.]+)
    OUTPUT_STRING=$TUMBLE,$FINETUNE,$TRANSFORMED,$TRAIN_DATASET,$TEST_DATASET,$DEPTH,$SAE

    TIME=$(cat $output | grep -E "TEST,time,mean" | cut -d ',' -f 4)
    F1=$(cat $output | grep -E "TEST,F1-score,global" | cut -d ',' -f 4)
    IOU=$(cat $output | grep -E "TEST,IOU,global" | cut -d ',' -f 4)
    AUC=$(cat $output | grep -E "TEST,AUC,global" | cut -d ',' -f 4)

    echo $OUTPUT_STRING,$TIME,$F1,$AUC,$IOU
done
