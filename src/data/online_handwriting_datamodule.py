from typing import Any, Dict, Optional, Tuple
from pathlib import Path

import torch
from lightning import LightningDataModule
from torch.utils.data import ConcatDataset, DataLoader, Dataset, random_split
from torchvision.datasets import MNIST
from torchvision.transforms import transforms

from src.data.online_handwriting_datasets import XournalPagewiseDataset
from src.data.online_handwriting_datasets import IAM_OnDB_Dataset
from src.data.online_handwriting_datasets import IAM_OnDB_Dataset_Carbune2020
from src.data.transforms import TwoChannels
from src.data.transforms import CharactersToIndices
from src.data.collate_functions import ctc_loss_collator
from src.data.transforms import TwoChannels
from src.data.transforms import Carbune2020
from src.data.transforms import DictToTensor
from src.data.transforms import SimpleNormalise
from src.data.tokenisers import AlphabetMapper
from src.data.online_handwriting_datasets import get_alphabet_from_dataset
from src.data.online_handwriting_datasets import get_number_of_channels_from_dataset


class IAMOnDBDataModule(LightningDataModule):
    """DataModule that wraps around datasets, provides data loaders
    and is used by PyTorch Lightning Trainer."""

    def __init__(
        self,
        data_dir: str = "data/",
        train_val_test_split: Tuple[int, int, int] = (55_000, 5_000, 10_000),
        batch_size: int = 64,
        num_workers: int = 0,
        limit: int = -1,
        pin_memory: bool = False,
        transform: str = "iam_xy",
    ) -> None:
        """Initialize an `IAMOnDBDataModule` instance.

        :param data_dir: The data directory. Defaults to `"data/"`.
        :param train_val_test_split: The train, validation and test split. Defaults to `(55_000, 5_000, 10_000)`.
        :param batch_size: The batch size. Defaults to `64`.
        :param num_workers: The number of workers. Defaults to `0`.
        :param limit: Limit the number of samples to this value. Useful for debugging.
        :param pin_memory: Whether to pin memory. Defaults to `False`.
        :param transform: Determines the dataset and transform to use.
        """
        super().__init__()

        # this line allows to access init params with 'self.hparams' attribute
        # also ensures init params will be stored in ckpt
        self.save_hyperparameters(logger=False)

        self.data_train: Optional[Dataset] = None
        self.data_val: Optional[Dataset] = None
        self.data_test: Optional[Dataset] = None

        self.batch_size_per_device = batch_size

    def setup(self, stage: Optional[str] = None) -> None:
        """Load data.
        
        Set variables `self.data_train`, `self.data_val` and `self.data_test`.

        :param stage: The stage to setup. Either `"fit"`, `"validate"`, `"test"`, or `"predict"`. Defaults to ``None``.
        """

        if not self.data_train and not self.data_val and not self.data_test:

            if self.hparams.transform == 'iam_xy':

                self.dataset = IAM_OnDB_Dataset(
                        Path(self.hparams.data_dir),
                        transform=None,
                        limit=self.hparams.limit,
                )

                if sum(self.hparams.train_val_test_split) > len(self.dataset):
                    raise RuntimeError(
                        f"Dataset (len={len(self.dataset)}) too short for requested splits ({self.hparams.train_val_test_split})."
                    )

                self.alphabet = get_alphabet_from_dataset( self.dataset )
                self.alphabet_mapper = AlphabetMapper( self.alphabet )

                transform = transforms.Compose([
                    TwoChannels(),
                    CharactersToIndices( self.alphabet ),
                ])

                self.dataset.transform = transform

            elif self.hparams.transform == 'carbune2020_xytn':

                self.dataset = IAM_OnDB_Dataset_Carbune2020(
                        Path(self.hparams.data_dir),
                        transform=None,
                        limit=self.hparams.limit,
                )

                if sum(self.hparams.train_val_test_split) > len(self.dataset):
                    raise RuntimeError(
                        f"Dataset (len={len(self.dataset)}) too short for requested splits ({self.hparams.train_val_test_split})."
                    )

                self.alphabet = get_alphabet_from_dataset( self.dataset )
                self.alphabet_mapper = AlphabetMapper( self.alphabet )

                transform = transforms.Compose([
                    DictToTensor(['x', 'y', 't', 'n']),
                    CharactersToIndices( self.alphabet ),
                ])

                self.dataset.transform = transform

            elif self.hparams.transform == 'carbune2020_xyn':

                self.dataset = IAM_OnDB_Dataset_Carbune2020(
                        Path(self.hparams.data_dir),
                        transform=None,
                        limit=self.hparams.limit,
                )

                if sum(self.hparams.train_val_test_split) > len(self.dataset):
                    raise RuntimeError(
                        f"Dataset (len={len(self.dataset)}) too short for requested splits ({self.hparams.train_val_test_split})."
                    )

                self.alphabet = get_alphabet_from_dataset( self.dataset )
                self.alphabet_mapper = AlphabetMapper( self.alphabet )

                transform = transforms.Compose([
                    DictToTensor(['x', 'y', 'n']),
                    CharactersToIndices( self.alphabet ),
                ])

                self.dataset.transform = transform

            elif self.hparams.transform == 'XournalPagewise_carbune_xyn':

                self.dataset = XournalPagewiseDataset(
                    self.hparams.data_dir,
                    transform=None,
                )

                if sum(self.hparams.train_val_test_split) > len(self.dataset):
                    raise RuntimeError(
                        f"Dataset (len={len(self.dataset)}) too short for requested splits ({self.hparams.train_val_test_split})."
                    )

                self.alphabet = get_alphabet_from_dataset( self.dataset )
                self.alphabet_mapper = AlphabetMapper( self.alphabet )

                transform = transforms.Compose([
                    Carbune2020(),
                    DictToTensor(['x', 'y', 'n']),
                    CharactersToIndices( self.alphabet ),
                ])

                self.dataset.transform = transform

            elif self.hparams.transform == 'iam_SimpleNormalise_xyn':

                self.dataset = IAM_OnDB_Dataset(
                        Path(self.hparams.data_dir),
                        transform=None,
                        limit=self.hparams.limit,
                )

                if sum(self.hparams.train_val_test_split) > len(self.dataset):
                    raise RuntimeError(
                        f"Dataset (len={len(self.dataset)}) too short for requested splits ({self.hparams.train_val_test_split})."
                    )

                self.alphabet = get_alphabet_from_dataset( self.dataset )
                self.alphabet_mapper = AlphabetMapper( self.alphabet )

                transform = transforms.Compose([
                    SimpleNormalise(),
                    DictToTensor(['x', 'y', 'n']),
                    CharactersToIndices( self.alphabet ),
                ])

                self.dataset.transform = transform

            elif self.hparams.transform == 'XournalPagewise_SimpleNormalise_xyn':

                self.dataset = XournalPagewiseDataset(
                    Path(self.hparams.data_dir),
                    transform=None,
                )

                if sum(self.hparams.train_val_test_split) > len(self.dataset):
                    raise RuntimeError(
                        f"Dataset (len={len(self.dataset)}) too short for requested splits ({self.hparams.train_val_test_split})."
                    )

                self.alphabet = get_alphabet_from_dataset( self.dataset )
                self.alphabet_mapper = AlphabetMapper( self.alphabet )

                transform = transforms.Compose([
                    SimpleNormalise(),
                    DictToTensor(['x', 'y', 'n']),
                    CharactersToIndices( self.alphabet ),
                ])

                self.dataset.transform = transform

            else:
                raise ValueError('`transform` set to non-existent value')

            self.number_of_channels = get_number_of_channels_from_dataset( self.dataset )

            self.data_train, self.data_val, self.data_test = random_split(
                dataset=self.dataset,
                lengths=self.hparams.train_val_test_split,
                generator=torch.Generator().manual_seed(42),
            )
            
    def train_dataloader(self) -> DataLoader[Any]:
        """Create and return the train dataloader.

        :return: The train dataloader.
        """
        return DataLoader(
            dataset=self.data_train,
            batch_size=self.batch_size_per_device,
            num_workers=self.hparams.num_workers,
            pin_memory=self.hparams.pin_memory,
            shuffle=True,
            collate_fn=ctc_loss_collator,
        )

    def val_dataloader(self) -> DataLoader[Any]:
        """Create and return the validation dataloader.

        :return: The validation dataloader.
        """
        return DataLoader(
            dataset=self.data_val,
            batch_size=self.batch_size_per_device,
            num_workers=self.hparams.num_workers,
            pin_memory=self.hparams.pin_memory,
            shuffle=False,
            collate_fn=ctc_loss_collator,
        )

    def test_dataloader(self) -> DataLoader[Any]:
        """Create and return the test dataloader.

        :return: The test dataloader.
        """
        return DataLoader(
            dataset=self.data_test,
            batch_size=self.batch_size_per_device,
            num_workers=self.hparams.num_workers,
            pin_memory=self.hparams.pin_memory,
            shuffle=False,
            collate_fn=ctc_loss_collator,
        )