#!/usr/bin/env python
"""Submit the ParallelAddWorkChain to thor_async."""

from aiida import load_profile, orm
from aiida.engine import submit
from parallel_add import ParallelAddWorkChain

if __name__ == '__main__':
    load_profile()

    # Get the code for thor_async computer
    code = orm.load_code('add@localhost_async')
    # code = orm.load_code('add@localhost')

    # Set up inputs
    inputs = {
        'code': code,
        'num_calculations': orm.Int(4),
        'base_x': orm.Int(1),
        'base_y': orm.Int(10),
    }

    # Submit the workchain
    node = submit(ParallelAddWorkChain, **inputs)
    print(f'Submitted ParallelAddWorkChain with PK: {node.pk}')
    print(f'Monitor with: verdi process status {node.pk}')
    print(f'View report: verdi process report {node.pk}')
