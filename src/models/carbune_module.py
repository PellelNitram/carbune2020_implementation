from typing import Any, Dict, Tuple
from pathlib import Path

import torch
from torch import nn
from lightning import LightningModule
from torchmetrics import MaxMetric, MeanMetric
from torchmetrics.classification.accuracy import Accuracy
from torchmetrics.functional.text import word_error_rate
from torchmetrics.functional.text import char_error_rate
from lightning.pytorch.loggers.tensorboard import TensorBoardLogger

from src.utils.decoders import GreedyCTCDecoder
from src.models.components.carbune2020_net import Carbune2020NetAttempt1
from src.utils.io import store_alphabet
from src.data.tokenisers import AlphabetMapper


class CarbuneLitModule2(LightningModule):

    def __init__(
        self,
        decoder,
        net: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: torch.optim.lr_scheduler,
    ) -> None:
        super().__init__()

        # this line allows to access init params with 'self.hparams' attribute
        # also ensures init params will be stored in ckpt
        self.save_hyperparameters(logger=False)

        self.decoder = decoder

        # loss function
        self.criterion = torch.nn.CTCLoss(blank=0, reduction='mean')

        # for averaging loss across batches
        self.train_loss = MeanMetric()
        self.val_loss = MeanMetric()
        self.test_loss = MeanMetric()

        # for averaging wer across batches
        self.train_wer = MeanMetric()
        self.val_wer = MeanMetric()
        self.test_wer = MeanMetric()

        # for averaging cer across batches
        self.train_cer = MeanMetric()
        self.val_cer = MeanMetric()
        self.test_cer = MeanMetric()

        # for tracking best so far validation accuracy
        self.val_acc_best = MaxMetric()

    def setup(self, stage: str) -> None:
        """Lightning hook that is called at the beginning of fit (train + validate), validate,
        test, or predict.

        This is a good hook when you need to build models dynamically or adjust something about
        them. This hook is called on every process when using DDP.

        :param stage: Either `"fit"`, `"validate"`, `"test"`, or `"predict"`.
        """

        dm = self.trainer.datamodule

        self.alphabet_mapper = dm.alphabet_mapper

        self.net = self.hparams.net(
            number_of_channels=dm.number_of_channels,
            alphabet=dm.alphabet,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Perform a forward pass through the model `self.net`.

        :param x: A tensor of images.
        :return: A tensor of logits.
        """
        return self.net(x)

    def on_train_start(self) -> None:
        self.val_loss.reset()

    def model_step(
        self, batch: Tuple[torch.Tensor, torch.Tensor]
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Perform a single model step on a batch of data.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target labels.

        :return: A tuple containing (in order):
            - A tensor of losses.
            - A tensor of predictions.
            - A tensor of target labels.
        """
        log_softmax = self.forward(batch['ink'])
        loss = self.criterion(
            log_softmax,
            batch['label'],
            batch['ink_lengths'],
            batch['label_lengths'],
        )
        decoded_texts = self.decoder(log_softmax, self.alphabet_mapper)

        # TODO: Could be pre-computed (using list0 in batch to avoid endless recomputation
        labels = []
        for i_batch in range(log_softmax.shape[1]):
            label_length = batch['label_lengths'][i_batch]
            label = batch['label'][i_batch, :label_length]
            label = [ self.alphabet_mapper.index_to_character(c) for c in label ]
            label = "".join(label)
            labels.append(label)

        cer = char_error_rate(preds=decoded_texts, target=labels)
        wer = word_error_rate(preds=decoded_texts, target=labels)

        metrics = {
            'cer': cer,
            'wer': wer,
        }

        return loss, metrics

    def training_step(
        self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int
    ) -> torch.Tensor:
        """Perform a single training step on a batch of data from the training set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        :return: A tensor of losses between model predictions and targets.
        """
        loss, metrics = self.model_step(batch)

        # update and log metrics
        self.train_loss(loss)
        self.log("train/loss", self.train_loss, on_step=False, on_epoch=True, prog_bar=True)

        self.train_wer(metrics['wer'])
        self.log("train/wer", self.train_wer, on_step=False, on_epoch=True, prog_bar=True)

        self.train_cer(metrics['cer'])
        self.log("train/cer", self.train_cer, on_step=False, on_epoch=True, prog_bar=True)

        # # TODO: Add text to log like tensorboard - what to save exactly? saving full text is too wasteful every step - every few steps??
        # for logger in self.loggers:
        #     if isinstance(logger, TensorBoardLogger):
        #         tensorboard = logger.experiment
        #         tensorboard.add_text('test_text', f'this is a test - {self.global_step}', self.global_step)

        # return loss or backpropagation will fail
        return loss

    def validation_step(self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int) -> None:
        """Perform a single validation step on a batch of data from the validation set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        """
        loss, metrics = self.model_step(batch)

        # update and log metrics
        self.val_loss(loss)
        self.log("val/loss", self.val_loss, on_step=False, on_epoch=True, prog_bar=True)

        self.val_wer(metrics['wer'])
        self.log("val/wer", self.val_wer, on_step=False, on_epoch=True, prog_bar=True)

        self.val_cer(metrics['cer'])
        self.log("val/cer", self.val_cer, on_step=False, on_epoch=True, prog_bar=True)

        # Log hyperparameter metric as explained here:
        # https://lightning.ai/docs/pytorch/stable/extensions/logging.html#logging-hyperparameters
        self.log("hp_metric", self.val_loss)

    def test_step(self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int) -> None:
        """Perform a single test step on a batch of data from the test set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        """
        loss, metrics = self.model_step(batch)

        # update and log metrics
        self.test_loss(loss)
        self.log("test/loss", self.test_loss, on_step=False, on_epoch=True, prog_bar=True)

    def configure_optimizers(self) -> Dict[str, Any]:
        """Choose what optimizers and learning-rate schedulers to use in your optimization.
        Normally you'd need one. But in the case of GANs or similar you might have multiple.

        Examples:
            https://lightning.ai/docs/pytorch/latest/common/lightning_module.html#configure-optimizers

        :return: A dict containing the configured optimizers and learning-rate schedulers to be used for training.
        """
        optimizer = self.hparams.optimizer(params=self.trainer.model.parameters())
        if self.hparams.scheduler is not None:
            scheduler = self.hparams.scheduler(optimizer=optimizer)
            return {
                "optimizer": optimizer,
                "lr_scheduler": {
                    "scheduler": scheduler,
                    "monitor": "val/loss",
                    "interval": "epoch",
                    "frequency": 1,
                },
            }
        return {"optimizer": optimizer}

    def on_fit_start(self):

        # Store data for subsequent inference: alphabet
        dm = self.trainer.datamodule
        store_alphabet(
            outfile=Path(self.trainer.default_root_dir) / 'alphabet.json',
            alphabet=dm.alphabet,
        )

class LitModule1(LightningModule):

    def __init__(
        self,
        nodes_per_layer: int,
        number_of_layers: int,
        dropout: float,
        decoder,
        optimizer: torch.optim.Optimizer,
        scheduler: torch.optim.lr_scheduler,
        alphabet: list[str],
        number_of_channels:int,
    ) -> None:
        super().__init__()

        # this line allows to access init params with 'self.hparams' attribute
        # also ensures init params will be stored in ckpt
        self.save_hyperparameters(logger=False)

        self.alphabet = list(alphabet)
        self.alphabet_mapper = AlphabetMapper(self.alphabet)

        # loss function
        self.criterion = torch.nn.CTCLoss(blank=0, reduction='mean')

        # ==============
        # Network layers
        # ==============

        # I would have loved to set up this module in `setup` but I was not able to
        # load checkpoints then, see e.g. https://github.com/Lightning-AI/pytorch-lightning/issues/5410

        # Output layer to be fed into CTC loss; the output must be log probabilities
        # according to https://pytorch.org/docs/stable/generated/torch.nn.CTCLoss.html
        # with shape (T, N, C) where C is the number of classes (= here alphabet letters)
        # N is the batch size and T is the sequence length
        self.log_softmax = nn.LogSoftmax(dim=2) # See this documentation:
                                                # https://pytorch.org/docs/stable/generated/torch.nn.LogSoftmax.html#torch.nn.LogSoftmax

        # Documentation: https://pytorch.org/docs/stable/generated/torch.nn.LSTM.html
        self.lstm_stack = torch.nn.LSTM(
            input_size=number_of_channels,
            hidden_size=nodes_per_layer,
            num_layers=number_of_layers,
            bias=True,
            batch_first=False,
            dropout=dropout,
            bidirectional=True,
            proj_size=0,
        )

        # Documentation: https://pytorch.org/docs/stable/generated/torch.nn.Linear.html
        self.linear = torch.nn.Linear(
            in_features=2 * nodes_per_layer, # 2 b/c bidirectional=True
            out_features=len(self.alphabet) + 1, # +1 for blank
            bias=True,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Perform a forward pass through the model.

        :param x: The input tensor.
        :return: A tensor of predictions. TODO: What's the shape? Needs to be added b/c useful.
        """
        result, (h_n, c_n) = self.lstm_stack(x) # TODO: Add explicit (h_0, c_0)
        result = self.linear(result)
        result = self.log_softmax(result)
        return result

    def model_step(
        self, batch: Tuple[torch.Tensor, torch.Tensor]
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Perform a single model step on a batch of data.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target labels.

        :return: A tuple containing (in order):
            - A tensor of losses.
            - A tensor of predictions.
            - A tensor of target labels.
        """
        log_softmax = self.forward(batch['ink'])
        loss = self.criterion(
            log_softmax,
            batch['label'],
            batch['ink_lengths'],
            batch['label_lengths'],
        )

        metrics = {
        }

        return loss, metrics

    def training_step(
        self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int
    ) -> torch.Tensor:
        """Perform a single training step on a batch of data from the training set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        :return: A tensor of losses between model predictions and targets.
        """
        loss, metrics = self.model_step(batch)

        self.batch_size = batch['ink'].shape[1]

        # update and log metrics
        self.log("train/loss", loss, on_step=False, on_epoch=True, prog_bar=True, batch_size=self.batch_size)

        # # TODO: Add text to log like tensorboard - what to save exactly? saving full text is too wasteful every step - every few steps??
        # for logger in self.loggers:
        #     if isinstance(logger, TensorBoardLogger):
        #         tensorboard = logger.experiment
        #         tensorboard.add_text('test_text', f'this is a test - {self.global_step}', self.global_step)

        # return loss or backpropagation will fail
        return loss

    def validation_step(self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int) -> None:
        """Perform a single validation step on a batch of data from the validation set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        """
        loss, metrics = self.model_step(batch)

        self.batch_size = batch['ink'].shape[1]

        # update and log metrics
        self.log("val/loss", loss, on_step=False, on_epoch=True, prog_bar=True, batch_size=self.batch_size)

        # Log hyperparameter metric as explained here:
        # https://lightning.ai/docs/pytorch/stable/extensions/logging.html#logging-hyperparameters
        self.log("hp_metric", loss, batch_size=self.batch_size)

    def test_step(self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int) -> None:
        """Perform a single test step on a batch of data from the test set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        """
        loss, metrics = self.model_step(batch)

        self.batch_size = batch['ink'].shape[1]

        # update and log metrics
        self.log("test/loss", loss, on_step=False, on_epoch=True, prog_bar=True, batch_size=self.batch_size)

    def configure_optimizers(self) -> Dict[str, Any]:
        """Choose what optimizers and learning-rate schedulers to use in your optimization.
        Normally you'd need one. But in the case of GANs or similar you might have multiple.

        Examples:
            https://lightning.ai/docs/pytorch/latest/common/lightning_module.html#configure-optimizers

        :return: A dict containing the configured optimizers and learning-rate schedulers to be used for training.
        """
        optimizer = self.hparams.optimizer(params=self.trainer.model.parameters())
        if self.hparams.scheduler is not None:
            scheduler = self.hparams.scheduler(optimizer=optimizer)
            return {
                "optimizer": optimizer,
                "lr_scheduler": {
                    "scheduler": scheduler,
                    "monitor": "val/loss",
                    "interval": "epoch",
                    "frequency": 1,
                },
            }
        return {"optimizer": optimizer}

    def on_fit_start(self):

        # Store data for subsequent inference: alphabet
        dm = self.trainer.datamodule
        store_alphabet(
            outfile=Path(self.trainer.default_root_dir) / 'alphabet.json',
            alphabet=dm.alphabet,
        )