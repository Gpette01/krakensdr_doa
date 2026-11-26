# shmemIface.inShmemIface.read_fw_ctr_fifo when the DAQ closes its end of the control FIFO (finding T-03).
import os

import pytest


@pytest.fixture
def reader_with_closed_writer(tmp_path):
    from shmemIface import inShmemIface

    path = tmp_path / "fw_delay_sync_iq"
    os.mkfifo(path)
    read_fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    write_fd = os.open(path, os.O_WRONLY)
    os.write(write_fd, bytes([1]))
    os.close(write_fd)  # the DAQ went away after one "buffer A ready"
    reader = inShmemIface.__new__(inShmemIface)  # no shared memory needed for the FIFO logic
    reader.fw_ctr_fifo = read_fd
    reader.num_read_attempts = 3
    yield reader
    os.close(read_fd)


def test_a_closed_fifo_is_reported_as_no_signal(reader_with_closed_writer):
    assert reader_with_closed_writer.wait_buff_free() == 0  # the byte written before the close
    assert reader_with_closed_writer.read_fw_ctr_fifo() is None  # end of file: no signal, no struct.error
    assert reader_with_closed_writer.wait_buff_free() == -1
