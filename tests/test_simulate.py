from pathlib import Path

from mdensemble.simulate import MDSimulationSettings, run_simulation

DATA_PATH = Path(__file__).parent.parent / "data"


def test_run_simulation() -> None:
    config = MDSimulationSettings(
        solvent_type="explicit",
        simulation_length_ns=0.1,
        report_interval_ps=0.1,
        explicit_barostat="MonteCarloAnisotropicBarostat",
    )

    input_dir = Path(DATA_PATH / "test_systems" / "COMPND236_1")
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)

    run_simulation(input_dir, output_dir, config)
