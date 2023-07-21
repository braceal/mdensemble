from argparse import ArgumentParser
from pathlib import Path

from mdensemble.simulate import MDSimulationSettings, run_simulation

DATA_PATH = Path(__file__).parent.parent / "data"


def _test_run_simulation(
    simulation_length_ns: float, report_interval_ps: float
) -> None:
    config = MDSimulationSettings(
        solvent_type="explicit",
        simulation_length_ns=simulation_length_ns,
        report_interval_ps=report_interval_ps,
        explicit_barostat="MonteCarloAnisotropicBarostat",
    )

    input_dir = Path(DATA_PATH / "test_systems" / "COMPND236_1")
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)

    run_simulation(input_dir, output_dir, config)


def test_run_simulation() -> None:
    _test_run_simulation(simulation_length_ns=0.02, report_interval_ps=10)


if __name__ == "__main__":
    # Entry point to test different configurations to check the ns/day
    parser = ArgumentParser()
    parser.add_argument("-n", "--simulation_length_ns", type=float, default=0.02)
    parser.add_argument("-r", "--report_interval_ps", type=float, default=10)
    args = parser.parse_args()
    _test_run_simulation(args.simulation_length_ns, args.report_interval_ps)
