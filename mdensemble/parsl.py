"""Utilities to build Parsl configurations."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from pathlib import Path
from typing import Literal
from typing import Sequence
from typing import Union

from parsl.config import Config
from parsl.executors import HighThroughputExecutor
from parsl.launchers import MpiExecLauncher
from parsl.providers import LocalProvider
from parsl.providers import PBSProProvider
from pydantic import Field

from mdensemble.utils import BaseModel


class BaseComputeConfig(BaseModel, ABC):
    """Compute settings (HPC platform, number of GPUs, etc)."""

    name: Literal[''] = ''
    """Name of the platform to use."""

    @abstractmethod
    def get_parsl_config(self, run_dir: str | Path) -> Config:
        """Create a new Parsl configuration.

        Parameters
        ----------
        run_dir : str | Path
            Path to store monitoring DB and parsl logs.

        Returns
        -------
        Config
            Parsl configuration.
        """
        ...


class LocalConfig(BaseComputeConfig):
    """Configuration for running on a local machine."""

    name: Literal['local'] = 'local'  # type: ignore[assignment]
    max_workers: int = Field(
        default=1,
        description='Number of workers to use.',
    )
    cores_per_worker: float = Field(
        default=0.0001,
        description='Number of cores per worker.',
    )

    def get_parsl_config(self, run_dir: str | Path) -> Config:
        """Create a Parsl configuration for running on a local machine."""
        return Config(
            run_dir=str(run_dir),
            strategy=None,
            executors=[
                HighThroughputExecutor(
                    address='localhost',
                    label='htex',
                    max_workers_per_node=self.max_workers,
                    cores_per_worker=self.cores_per_worker,
                    worker_port_range=(10000, 20000),
                    provider=LocalProvider(init_blocks=1, max_blocks=1),
                ),
            ],
        )


class WorkstationConfig(BaseComputeConfig):
    """Compute config for a GPU workstation."""

    name: Literal['workstation'] = 'workstation'  # type: ignore[assignment]

    available_accelerators: int | Sequence[str] = Field(
        default=1,
        description='Number of GPU accelerators to use.',
    )
    retries: int = Field(
        default=1,
        description='Number of retries for the task.',
    )

    def get_parsl_config(self, run_dir: str | Path) -> Config:
        """Generate a Parsl configuration for workstation execution."""
        return Config(
            run_dir=str(run_dir),
            retries=self.retries,
            executors=[
                HighThroughputExecutor(
                    address='localhost',
                    label='htex',
                    cpu_affinity='block',
                    available_accelerators=self.available_accelerators,
                    worker_port_range=(10000, 20000),
                    provider=LocalProvider(init_blocks=1, max_blocks=1),
                ),
            ],
        )


class PolarisConfig(BaseComputeConfig):
    """Polaris@ALCF configuration.

    See here for details: https://docs.alcf.anl.gov/polaris/workflows/parsl/
    """

    name: Literal['polaris'] = 'polaris'  # type: ignore[assignment]

    num_nodes: int = Field(
        default=1,
        description='Number of nodes to request.',
    )
    worker_init: str = Field(
        default='',
        description='Command to be run before starting a worker. '
        'Load any modules and environments, etc.',
    )
    scheduler_options: str = Field(
        default='#PBS -l filesystems=home:eagle:grand',
        description='PBS directives, pass -J for array jobs.',
    )
    account: str = Field(
        ...,
        description='The account to charge compute to.',
    )
    queue: str = Field(
        ...,
        description='Which queue to submit jobs to, will usually be prod.',
    )
    walltime: str = Field(
        ...,
        description='Maximum job time.',
    )
    cpus_per_node: int = Field(
        default=32,
        description='Up to 64 with multithreading.',
    )
    cores_per_worker: float = Field(
        default=8,
        description='Number of cores per worker. '
        'Evenly distributed between GPUs.',
    )
    retries: int = Field(
        default=0,
        description='Number of retries upon failure.',
    )
    worker_debug: bool = Field(
        default=False,
        description='Enable worker debug.',
    )

    def get_parsl_config(self, run_dir: str | Path) -> Config:
        """Create a parsl configuration for running on Polaris@ALCF.

        We will launch 4 workers per node, each pinned to a different GPU.

        Parameters
        ----------
        run_dir: PathLike
            Directory in which to store Parsl run files.
        """
        return Config(
            executors=[
                HighThroughputExecutor(
                    label='htex',
                    heartbeat_period=15,
                    heartbeat_threshold=120,
                    worker_debug=self.worker_debug,
                    # available_accelerators will override settings
                    # for max_workers
                    available_accelerators=4,
                    cores_per_worker=self.cores_per_worker,
                    # address=address_by_interface('bond0'),
                    cpu_affinity='block-reverse',
                    prefetch_capacity=0,
                    provider=PBSProProvider(
                        launcher=MpiExecLauncher(
                            bind_cmd='--cpu-bind',
                            overrides='--depth=64 --ppn 1',
                        ),
                        account=self.account,
                        queue=self.queue,
                        select_options='ngpus=4',
                        # PBS directives: for array jobs pass '-J' option
                        scheduler_options=self.scheduler_options,
                        # Command to be run before starting a worker, such as:
                        worker_init=self.worker_init,
                        # number of compute nodes allocated for each block
                        nodes_per_block=self.num_nodes,
                        init_blocks=1,
                        min_blocks=0,
                        max_blocks=1,  # Increase to have more parallel jobs
                        cpus_per_node=self.cpus_per_node,
                        walltime=self.walltime,
                    ),
                ),
            ],
            run_dir=str(run_dir),
            # checkpoint_mode='task_exit',
            retries=self.retries,
            app_cache=True,
        )


class SunspotConfig(BaseComputeConfig):
    """Configuration for running on Sunspot.

    Each GPU tasks uses a single tile.
    """

    name: Literal['sunspot'] = 'sunspot'  # type: ignore[assignment]

    worker_init: str = Field(
        default='',
        description='Command to be run before starting a worker. '
        'Load any modules and environments, etc.',
    )
    num_nodes: int = Field(
        default=1,
        description='Number of nodes to request.',
    )
    scheduler_options: str = Field(
        default='',
        description='PBS directives, pass -J for array jobs.',
    )
    account: str = Field(
        ...,
        description='The account to charge compute to.',
    )
    queue: str = Field(
        ...,
        description='Which queue to submit jobs to, will usually be prod.',
    )
    walltime: str = Field(
        ...,
        description='Maximum job time.',
    )
    retries: int = Field(
        default=0,
        description='Number of retries upon failure.',
    )
    cpus_per_node: int = Field(
        default=208,
        description='Number of cores per node.',
    )

    def get_parsl_config(self, run_dir: str | Path) -> Config:
        """Create a Parsl configuration for running on Sunspot."""
        accel_ids = [f'{gid}.{tid}' for gid in range(6) for tid in range(2)]
        return Config(
            executors=[
                HighThroughputExecutor(
                    label='htex',
                    # Ensures one worker per accelerator
                    available_accelerators=accel_ids,
                    cpu_affinity='block',  # Assigns cpus in sequential order
                    prefetch_capacity=0,
                    max_workers_per_node=12,
                    cores_per_worker=16,
                    heartbeat_period=30,
                    heartbeat_threshold=300,
                    worker_debug=False,
                    # Ensures 1 manager per node and allows it to
                    # divide work among all 208 threads
                    provider=PBSProProvider(
                        launcher=MpiExecLauncher(
                            bind_cmd='--cpu-bind',
                            overrides='--depth=208 --ppn 1',
                        ),
                        worker_init=self.worker_init,
                        nodes_per_block=self.num_nodes,
                        account=self.account,
                        queue=self.queue,
                        walltime=self.walltime,
                    ),
                ),
            ],
            run_dir=str(run_dir),
            checkpoint_mode='task_exit',
            retries=self.retries,
            app_cache=True,
        )


ComputeSettingsTypes = Union[
    LocalConfig,
    WorkstationConfig,
    PolarisConfig,
    SunspotConfig,
]
