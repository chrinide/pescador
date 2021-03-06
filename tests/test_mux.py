import pytest

import collections
import itertools
import numpy as np
import random

import pescador
import pescador.mux
import test_utils as T


def test_mux_single():

    reference = list(T.finite_generator(50))
    stream = pescador.Streamer(reference)

    mux = pescador.mux.Mux([stream], 1, with_replacement=False)
    estimate = list(mux)
    assert reference == estimate


@pytest.mark.parametrize('items',
                         [['X'], ['Y'], ['X', 'Y'], ['Y', 'X'],
                          pytest.mark.xfail([],
                                            raises=pescador.PescadorError)])
def test_mux_single_tuple(items):

    stream = pescador.Streamer(T.md_generator, 2, 50, items=items)
    reference = list(stream)

    mux = pescador.mux.Mux([stream], 1, with_replacement=False)
    estimate = list(mux.tuples(*items))

    assert len(reference) == len(estimate)
    for r, e in zip(reference, estimate):
        assert isinstance(e, tuple)
        for item, value in zip(items, e):
            assert np.allclose(r[item], value)


def test_mux_empty():
    with pytest.raises(pescador.PescadorError):
        list(pescador.mux.Mux([], 1))


@pytest.mark.parametrize('weight', [0.0, 0.5])
def test_mux_weighted(weight):
    reference = list(T.finite_generator(50))
    noise = list(T.finite_generator(50, size=1))
    stream = pescador.Streamer(reference)
    stream2 = pescador.Streamer(noise)
    mux = pescador.mux.Mux([stream, stream2], 2,
                           weights=[1.0, weight],
                           with_replacement=False)
    estimate = list(mux)
    if weight == 0.0:
        assert reference == estimate
    else:
        assert reference != estimate


# This should give us all the reference before all the noise
@pytest.mark.parametrize('weight', ([1e10, 1e-10],))
def test_mux_rare(weight):
    reference = list(T.finite_generator(50))
    noise = list(T.finite_generator(50, size=1))
    stream = pescador.Streamer(reference)
    stream2 = pescador.Streamer(noise)
    mux = pescador.mux.Mux([stream, stream2], 2,
                           weights=weight,
                           with_replacement=False)
    estimate = list(mux)
    assert (reference + noise) == estimate


def test_empty_streams():

    def __empty():
        if False:
            yield 1

    reference = pescador.Streamer(T.finite_generator, 10)
    empty = pescador.Streamer(__empty)

    mux = pescador.mux.Mux([reference, empty], 2, rate=None,
                           with_replacement=False,
                           weights=[1e-10, 1e10])
    estimate = list(mux.iterate(10))

    ref = list(reference)
    assert len(ref) == len(estimate)
    for b1, b2 in zip(ref, estimate):
        T.__eq_batch(b1, b2)


@pytest.mark.parametrize('n_streams', [1, 2, 4])
@pytest.mark.parametrize('n_samples', [10, 20, 80])
@pytest.mark.parametrize('k', [1, 2, 4])
@pytest.mark.parametrize('rate', [1.0, 2.0, 8.0])
@pytest.mark.parametrize('random_state',
                         [None,
                          1000,
                          np.random.RandomState(seed=1000),
                          pytest.mark.xfail('foo',
                                            raises=pescador.PescadorError)])
def test_mux_replacement(n_streams, n_samples, k, rate, random_state):
    streamers = [pescador.Streamer(T.infinite_generator)
                 for _ in range(n_streams)]

    mux = pescador.mux.Mux(streamers, k, rate=rate, random_state=random_state)

    estimate = list(mux.iterate(n_samples))

    # Make sure we get the right number of samples
    assert len(estimate) == n_samples


@pytest.mark.parametrize('n_streams', [1, 2, 4])
@pytest.mark.parametrize('n_samples', [512])
@pytest.mark.parametrize('k', [1, 2, 4])
@pytest.mark.parametrize('rate', [1.0, 2.0, 4.0])
def test_mux_revive(n_streams, n_samples, k, rate):
    streamers = [pescador.Streamer(T.finite_generator, 10)
                 for _ in range(n_streams)]

    mux = pescador.mux.Mux(streamers, k, rate=rate,
                           with_replacement=False,
                           revive=True)

    estimate = list(mux.iterate(n_samples))

    # Make sure we get the right number of samples
    # This is highly improbable when revive=False
    assert len(estimate) == n_samples


def test_mux_bad_streamers():
    with pytest.raises(pescador.PescadorError):
        steamers = [pescador.Streamer(T.finite_generator, 10)
                    for _ in range(5)]

        # 5 steamers, 10 weights, should trigger an error
        pescador.Mux(steamers, None, weights=np.random.randn(10))


def test_mux_bad_weights():
    with pytest.raises(pescador.PescadorError):
        streamers = [pescador.Streamer(T.finite_generator, 10)
                     for _ in range(5)]

        # 5 streamers, all-zeros weight vector should trigger an error
        pescador.Mux(streamers, None, weights=np.zeros(5))


def test_mux_of_muxes_itered():
    # Check on Issue #79
    abc = pescador.Streamer('abc')
    xyz = pescador.Streamer('xyz')
    mux1 = pescador.Mux([abc, xyz], k=10, rate=None,
                        prune_empty_streams=False, revive=True,
                        random_state=135)
    samples1 = mux1.iterate(max_iter=1000)
    count1 = collections.Counter(samples1)
    print(count1)
    assert set('abcxyz') == set(count1.keys())

    n123 = pescador.Streamer('123')
    n456 = pescador.Streamer('456')
    mux2 = pescador.Mux([n123, n456], k=10, rate=None,
                        prune_empty_streams=False, revive=True,
                        random_state=246)
    samples2 = mux2.iterate(max_iter=1000)
    count2 = collections.Counter(samples2)
    print(count2)
    assert set('123456') == set(count2.keys())

    # Note that (random_state=987, k=2) fails.
    mux3 = pescador.Mux([mux1, mux2], k=10, rate=None,
                        prune_empty_streams=False, revive=True,
                        random_state=987)
    samples3 = mux3.iterate(max_iter=1000)
    count3 = collections.Counter(samples3)
    print(count3)
    assert set('abcxyz123456') == set(count3.keys())


def test_mux_of_muxes_single():
    # Check on Issue #79
    abc = pescador.Streamer('abc')
    xyz = pescador.Streamer('xyz')
    mux1 = pescador.Mux([abc, xyz], k=2, rate=None, revive=True,
                        with_replacement=False,
                        prune_empty_streams=False)

    n123 = pescador.Streamer('123')
    n456 = pescador.Streamer('456')
    mux2 = pescador.Mux([n123, n456], k=2, rate=None, revive=True,
                        with_replacement=False,
                        prune_empty_streams=False)

    mux3 = pescador.Mux([mux1, mux2], k=2, rate=None,
                        with_replacement=False, revive=True,
                        prune_empty_streams=False)
    samples3 = list(mux3.iterate(max_iter=10000))
    count3 = collections.Counter(samples3)
    print(samples3[:10], count3)
    assert set('abcxyz123456') == set(count3.keys())


def test_critical_mux():
    # Check on Issue #80
    chars = 'abcde'
    streamers = [pescador.Streamer(x * 5) for x in chars]
    mux = pescador.Mux(streamers, k=len(chars), rate=None,
                       with_replacement=False, revive=True,
                       prune_empty_streams=False, random_state=135)
    samples = mux.iterate(max_iter=1000)
    print(collections.Counter(samples))


def test_critical_mux_of_rate_limited_muxes():
    # Check on Issue #79
    def _choice(vals):
        while True:
            yield random.choice(vals)

    ab = pescador.Streamer(_choice, 'ab')
    cd = pescador.Streamer(_choice, 'cd')
    ef = pescador.Streamer(_choice, 'ef')
    mux1 = pescador.Mux([ab, cd, ef], k=2, rate=2,
                        with_replacement=False, revive=True)

    gh = pescador.Streamer(_choice, 'gh')
    ij = pescador.Streamer(_choice, 'ij')
    kl = pescador.Streamer(_choice, 'kl')

    mux2 = pescador.Mux([gh, ij, kl], k=2, rate=2,
                        with_replacement=False, revive=True)

    mux3 = pescador.Mux([mux1, mux2], k=2, rate=None,
                        with_replacement=False, revive=True)
    samples = list(mux3.iterate(max_iter=10000))
    count = collections.Counter(samples)
    max_count, min_count = max(count.values()), min(count.values())
    assert (max_count - min_count) / max_count < 0.2
    print(count)
    assert set('abcdefghijkl') == set(count.keys())


def test_restart_mux():
    s1 = pescador.Streamer('abc')
    s2 = pescador.Streamer('def')
    mux = pescador.Mux([s1, s2], k=2, rate=None, revive=True,
                       with_replacement=False, random_state=1234)
    assert len(list(mux(max_iter=100))) == len(list(mux(max_iter=100)))


def test_sampled_mux_of_muxes():

    def _cycle(values):
        while True:
            for v in values:
                yield v

    # Build some sample streams
    ab = pescador.Streamer(_cycle, 'ab')
    cd = pescador.Streamer(_cycle, 'cd')
    ef = pescador.Streamer(_cycle, 'ef')
    mux1 = pescador.Mux([ab, cd, ef], k=3, rate=None,
                        with_replacement=False, revive=False)

    # And inspect the first mux
    samples1 = list(mux1(max_iter=6 * 10))
    count1 = collections.Counter(samples1)
    print(count1)
    assert set(count1.keys()) == set('abcdef')

    # Build another set of streams
    gh = pescador.Streamer(_cycle, 'gh')
    ij = pescador.Streamer(_cycle, 'ij')
    kl = pescador.Streamer(_cycle, 'kl')
    mux2 = pescador.Mux([gh, ij, kl], k=3, rate=None,
                        with_replacement=False, revive=False)

    # And inspect the second mux
    samples2 = list(mux2(max_iter=6 * 10))
    count2 = collections.Counter(samples2)
    print(count2)
    assert set(count2.keys()) == set('ghijkl')

    # Merge the muxes together.
    mux3 = pescador.Mux([mux1, mux2], k=2, rate=None,
                        with_replacement=False, revive=False)
    samples3 = list(mux3.iterate(max_iter=10000))
    count3 = collections.Counter(samples3)
    print(count3)
    assert set('abcdefghijkl') == set(count3.keys())
    max_count, min_count = max(count3.values()), min(count3.values())
    assert (max_count - min_count) / max_count < 0.2


@pytest.mark.timeout(1.0)
@pytest.mark.xfail(reason="Empty streams cause inf loop (#87)")
def test_mux_inf_loop():
    s1 = pescador.Streamer([])
    s2 = pescador.Streamer([])
    mux = pescador.Mux([s1, s2], k=2, rate=None, revive=True,
                       with_replacement=False, random_state=1234)

    assert len(list(mux(max_iter=100))) == 0
