import os
import sys
import pathlib
import argparse
import numpy as np
import logging
import glob
import shutil

script_dir = pathlib.Path(__file__).parent.absolute()
parent_dir = script_dir.parents[0]
sys.path.append(str(script_dir))
os.chdir(script_dir)
from utilities import natural_sort, match_input_files
from process_pyglider import proc_pyglider_l0
from recombine import recombine
from geocode import update_ncs

_log = logging.getLogger(__name__)


def batched_process(glider, mission):
    steps = [1, 1, 1, 1]
    batch_size = 100
    kind = "raw"

    # Process in batches of dives (default 100) to avoid maxxing out memory
    input_dir = f"/data/data_raw/complete_mission/SEA{glider}/M{mission}/"
    if not input_dir:
        raise ValueError(f"Input dir {input_dir} not found")
    output_dir = f"/data/data_l0_pyglider/complete_mission/SEA{glider}/M{mission}/"

    in_files_gli = natural_sort(glob.glob(f"{input_dir}*gli*"))
    in_files_pld = natural_sort(glob.glob(f"{input_dir}*pld*{kind}*"))
    in_files_gli, in_files_pld = match_input_files(in_files_gli, in_files_pld)

    if len(in_files_gli) == 0 or len(in_files_pld) == 0:
        raise ValueError(f"input dir {input_dir} does not contain gli and/or pld files")
    num_batches = int(np.ceil(len(in_files_gli) / batch_size))
    _log.info(f"Processing glider {glider} mission {mission} in {num_batches} batches")

    # If less than one batch worth, process directly
    if num_batches == 1:
        proc_pyglider_l0(glider, mission, kind, input_dir, output_dir, steps=steps)
        _log.info(f"Finished processing glider {glider} mission {mission} in {num_batches} batch")
        return
    # Process input files in batches
    num_files = len(in_files_gli)
    starts = np.arange(0, num_files, batch_size)
    ends = np.arange(batch_size, num_files + batch_size , batch_size)
    # fix for if we have 2 or fewer files in final batch
    if num_files - starts[-1] < 3:
        starts = starts[:-1]
        ends[-2] = ends[-1]
        ends = ends[:-1]
        _log.info(f"reduced to {len(starts)} batches")
    for i in range(len(starts)):
        start = starts[i]
        end = ends[i]
        in_sub_dir = f"{input_dir[:-1]}_sub_{i}/"
        if not pathlib.Path(in_sub_dir).exists():
            pathlib.Path(in_sub_dir).mkdir(parents=True)
        in_files_gli_sub = in_files_gli[start:end]
        in_files_pld_sub = in_files_pld[start:end]
        # Copy input into a sub directory
        for filename in in_files_gli_sub:
            shutil.copy(filename, in_sub_dir)
        for filename in in_files_pld_sub:
            shutil.copy(filename, in_sub_dir)
        # create output directory
        out_sub_dir = f"{output_dir[:-1]}_sub_{i}/"
        if not pathlib.Path(out_sub_dir).exists():
            pathlib.Path(out_sub_dir).mkdir(parents=True)
        # Process on sub-directory
        _log.info(f"Started processing glider {glider} mission {mission} batch {i}")
        proc_pyglider_l0(glider, mission, kind, in_sub_dir, out_sub_dir, steps=steps)
        _log.info(f"Finished processing glider {glider} mission {mission} batch {i}")

    _log.info('Batched processing complete')


if __name__ == '__main__':
    logf = f'/data/log/complete_mission_reprocess.log'
    logging.basicConfig(filename=logf,
                        filemode='w',
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        level=logging.INFO,
                        datefmt='%Y-%m-%d %H:%M:%S')
    _log.info("Start complete reprocessing")
    glider_paths = list(pathlib.Path("/data/data_l0_pyglider/complete_mission").glob("SEA*"))
    glidermissions = []
    for glider_path in glider_paths:
        mission_paths = glider_path.glob("M*")
        for mission_path in mission_paths:
            try:
                glidermissions.append((int(glider_path.parts[-1][3:]), int(mission_path.parts[-1][1:])))
            except:
                _log.warning(f"Could not process {mission_path}")

    for glider, mission in glidermissions:
        batched_process(glider, mission)
        recombine(glider, mission)
        # Call follow-up scripts
        update_ncs(glider, mission, 'complete_mission')
        sys.path.append(str(parent_dir / "quick-plots"))
        # noinspection PyUnresolvedReferences
        from complete_mission_plots import complete_plots
        complete_plots(glider, mission)
        _log.info("Finished plot creation")
        sys.path.append(str(parent_dir / "voto-web/voto/bin"))
        # noinspection PyUnresolvedReferences
        from add_profiles import init_db, add_complete_profiles
        init_db()
        add_complete_profiles(pathlib.Path(f"/data/data_l0_pyglider/complete_mission/SEA{glider}/M{mission}"))
        _log.info("Finished add to database")
