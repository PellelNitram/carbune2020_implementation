# First experiments using data with Carbune2020 transform

python src/train.py \
    --config-name experiment2.yaml \
    -m \
    data.batch_size=64 \
    trainer.max_epochs=10000 \
    data.limit=-1 \
    data.train_val_test_split="[1.0,0,0]" \
    model.optimizer.lr=0.0001 \
    data.pin_memory=True \
    data.num_workers=4 \
    data.transform="carbune2020_xytn" \
    tags="experiment5"