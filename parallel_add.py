"""WorkChain to submit multiple ArithmeticAddCalculation jobs in parallel."""

from aiida import orm
from aiida.calculations.arithmetic.add import ArithmeticAddCalculation
from aiida.engine import WorkChain


class ParallelAddWorkChain(WorkChain):
    """WorkChain that submits multiple ArithmeticAddCalculation jobs in parallel."""

    @classmethod
    def define(cls, spec):
        """Define the process specification."""
        super().define(spec)

        # Inputs
        spec.input('code', valid_type=orm.AbstractCode, help='The code to use for the calculations.')
        spec.input(
            'num_calculations',
            valid_type=orm.Int,
            default=lambda: orm.Int(5),
            help='Number of calculations to submit in parallel.',
        )
        spec.input(
            'base_x',
            valid_type=orm.Int,
            default=lambda: orm.Int(1),
            help='Base value for x operand (will be incremented for each calculation).',
        )
        spec.input(
            'base_y',
            valid_type=orm.Int,
            default=lambda: orm.Int(10),
            help='Base value for y operand (will be incremented for each calculation).',
        )

        # Outline
        spec.outline(
            cls.submit_calculations,
            cls.inspect_calculations,
            cls.results,
        )

        # Outputs
        spec.output('total_sum', valid_type=orm.Int, help='Sum of all calculation results.')
        spec.output('num_successful', valid_type=orm.Int, help='Number of successful calculations.')
        spec.output('num_failed', valid_type=orm.Int, help='Number of failed calculations.')

        # Exit codes
        spec.exit_code(
            400, 'ERROR_SOME_CALCULATIONS_FAILED', message='Some calculations failed to complete successfully.'
        )
        spec.exit_code(
            401, 'ERROR_ALL_CALCULATIONS_FAILED', message='All calculations failed to complete successfully.'
        )

    def submit_calculations(self):
        """Submit multiple ArithmeticAddCalculation jobs in parallel."""
        num_calcs = self.inputs.num_calculations.value
        base_x = self.inputs.base_x.value
        base_y = self.inputs.base_y.value

        self.report(f'Submitting {num_calcs} ArithmeticAddCalculation jobs in parallel...')

        # Submit all calculations and store in context
        for i in range(num_calcs):
            inputs = {
                'code': self.inputs.code,
                'x': orm.Int(base_x + i),
                'y': orm.Int(base_y + i),
            }

            future = self.submit(ArithmeticAddCalculation, **inputs)
            key = f'calc_{i}'
            self.to_context(**{key: future})

        self.report(f'Successfully submitted {num_calcs} calculations.')

    def inspect_calculations(self):
        """Inspect the results of all submitted calculations."""
        num_calcs = self.inputs.num_calculations.value
        num_successful = 0
        num_failed = 0
        total_sum = 0

        self.report('Inspecting calculation results...')

        for i in range(num_calcs):
            key = f'calc_{i}'
            calc_node = self.ctx[key]

            if calc_node.is_finished_ok:
                num_successful += 1
                result = calc_node.outputs.sum.value
                total_sum += result
                self.report(f'Calculation {i}: SUCCESS - Result = {result}')
            else:
                num_failed += 1
                exit_status = calc_node.exit_status
                self.report(f'Calculation {i}: FAILED - Exit status = {exit_status}')

        # Store results in context
        self.ctx.num_successful = num_successful
        self.ctx.num_failed = num_failed
        self.ctx.total_sum = total_sum

        self.report(f'Summary: {num_successful} successful, {num_failed} failed, ' f'total sum = {total_sum}')

        # Return exit code if any calculations failed
        if num_failed == num_calcs:
            return self.exit_codes.ERROR_ALL_CALCULATIONS_FAILED
        elif num_failed > 0:
            return self.exit_codes.ERROR_SOME_CALCULATIONS_FAILED

    def results(self):
        """Set the output nodes."""
        # Store nodes before outputting them to preserve provenance
        total_sum = orm.Int(self.ctx.total_sum).store()
        num_successful = orm.Int(self.ctx.num_successful).store()
        num_failed = orm.Int(self.ctx.num_failed).store()

        self.out('total_sum', total_sum)
        self.out('num_successful', num_successful)
        self.out('num_failed', num_failed)

        self.report(f'WorkChain completed with {self.ctx.num_successful} successful calculations.')
