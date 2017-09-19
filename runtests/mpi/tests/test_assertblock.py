from runtests.mpi import MPITest, nompi

@MPITest(commsize=[1, 2])
def test_assert_block(comm):
    error = None
    try:
        with nompi(comm):
            if comm.rank == 0:
                raise ValueError("This is an error raised on rank 0. Other ranks will see a RuntimeError instead")
    except RuntimeError as e:
        assert comm.rank != 0
    except ValueError as e:
        assert comm.rank == 0
        
