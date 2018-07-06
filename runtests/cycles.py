"""
    Finding reference cycles of objects.

    The analysis is more or less static and oriented for
    single thread applications. Use objgraph for some of 
    the lower level operations.

    main entry point is:

    .. code::

        assert_no_backcycles(*objs)

    This is not very powerful, as it works against the
    intuition: if objs references a cycle it won't find it.
    if only finds cycles that include objs.

    .. code::

        assert_no_cycles(*objs)

    will find cycles that started from objs, but there are
    in general too many false positives to make this of any
    practical usefulness.

"""

import gc

def assert_no_cycles(*objs):
    # FIXME: this needs culling -- but how?

    gc.collect()
    sccs = tarjan(objs, get_referrers=gc.get_referents)

    if len(sccs) > 0:
        show_cycles(sccs)

    assert len(sccs) == 0

def assert_no_backcycles(*objs):
    """ Assert no objects on the list induces any cycles
        in the back reference list.

        e.g. 

        .. code::

            a = 3O

            assert_no_backcycles(a)

            a = []
            b = [a]
            a[0] = b

            assert_no_backcycles(a)
    """
    gc.collect()
    sccs = tarjan(objs, get_referrers=gc.get_referrers)

    if len(sccs) > 0:
        show_cycles(sccs)

    assert len(sccs) == 0

def show_cycles(sccs, joined=False):
    import objgraph
    a = sccs
    if joined:
        a = []
        for scc in sccs:
            a.extend(scc)
        a = [a]

    for scc in a:
        objs = objgraph.at_addrs(scc)
        print(objgraph.typestats(objs))
        objgraph.show_backrefs(objs, max_depth=len(scc) + 5,
            filter=lambda x: id(x) in scc)

def isin(obj, l):
    # can not use 'in' because it checks for equality not identity.
    for x in l:
        if x is obj: return True
    return False

def ignore_frames(x):
    import inspect
    import types

    l = []
    if inspect.isclass(x):
        # must be a class object
        l.extend([x.__mro__, x.__dict__])

        if hasattr(x, '__weakref__'):
            l.extend([x.__weakref__])

        for member in x.__dict__.values():
            # ignore attributes.
            if inspect.isgetsetdescriptor(member):
                l.append(member)

    # ignore the module and module dict
    if inspect.ismodule(x):
        l.extend([x, x.__dict__])

    # ignore a frame; this will not work with multi-threaded applications
    # use refcycle in that case for live applications
    if inspect.isframe(x):
        # this can't detect multi-threaded.
        l.extend([x])

    return l

def tarjan(objs, get_referrers=gc.get_referrers,
        ignore=ignore_frames,
        getid=id,
        squeeze=True):
    """ Identifying strongly connected components from a directional graph.

        Algorithm is from

            https://en.wikipedia.org/wiki/Tarjan%27s_strongly_connected_components_algorithm

        Parameters
        ----------
        objs : list
            a list of objects to start the algorithm. The input graph consists of
            all objects connected to these objects by the get_referrers function.

        get_referrers: func(*objs)
            returns the neighbour of objects. This function represents the egdes and
            serves as the discovery function for vertices.

        squeeze : bool
            True, remove single item components except self-loops.

        getid : func(x)
            generates a unique id for the given object. ids are used to track objects

    """
    gindex = [0]
    index = {}
    lowlink = {}
    onStack = {}
    S = []

    id_to_obj = {}

    edges = {}

    # first traverse to obtain the full object list V,
    # and the id to object mapping,

    def bfs_action(x):
        id_to_obj[getid(x)] = x

    V = _bfs(objs,
            get_referrers,
            ignore=lambda x: ignore(x) + [id_to_obj],
            action=lambda x: id_to_obj.update({getid(x) : x}),
            getid=getid)

    # shrink id_to_obj to the same size as V, removing undesired objects
    id_to_obj = {k: id_to_obj[k] for k in V }

    #print('V', V)
    # initially, nothing is on the stack
    for v in V: onStack[v] = False

    def strongly_connect(v):
        sccs = []

        index[v] = gindex[0]
        lowlink[v] = gindex[0]
        gindex[0]  = gindex[0] + 1

        S.append(v)

        onStack[v] = True
        isloop = False

        W = []
        for w in _ignore_filter(get_referrers(id_to_obj[v]),
                          ignore=lambda x: [x] if getid(x) not in V else [],
                          extraids=set()
                          ):
            W.append(getid(w))

        for w in W:
            if w not in index:
                sccs.extend(strongly_connect(w))
                lowlink[v] = min(lowlink[v], lowlink[w])

            elif onStack[w]:
                lowlink[v] = min(lowlink[v], index[w])
                if v == w:
                    isloop = True

        if lowlink[v] == index[v]:
            # start a new strongly connected component
            scc = []
            while True:
                w = S.pop()
                onStack[w] = False
                # add w to the current strongly connected component
                scc.append(w)
                if w == v:
                    break

            # if the scc is singular and not
            # forming a loop, skip it.
            if len(scc) > 1 or isloop:
                # output
                sccs.append(scc)

        return sccs

    sccs = []
    for v in V:
        if v not in index:
            sccs.extend(strongly_connect(v))

    return sorted(sccs, key=lambda x:-len(x))

def _ignore_filter(referrers, ignore, extraids, getid=id):
    """ Ignore objects on the referrers list if ignore(x) is true or if x is in extra """
    r = []
    for ref in referrers:
        if ignore is not None:
            extraids.update(set([getid(o) for o in ignore(ref)]))

        if getid(ref) in extraids: continue

        r.append(ref)

    return r

def _bfs(objs, get_referrers, ignore=None, action=None, getid=id):
    """ A breadth first search traverse of the graph.
    """
    import types
    visited = set()
    referrers = list(objs)
    extraids = set()

    extraids.add(getid(objs))
    while True:
        front = []
        for ref in referrers:

            refid = getid(ref)

            if refid in visited:
                # already visited
                pass
            else:
                if action: action(ref)
                visited.add(refid)
                front.append(ref)

        if len(front) == 0:
            break

        extraids.add(getid(referrers))
        extraids.add(getid(front))

        newreferrers = get_referrers(*front)

        extraids.add(getid(newreferrers))

        referrers = _ignore_filter(newreferrers,
                ignore=ignore,
                extraids=extraids)

        #print(extraids)
        #print('referrers', [type(o) for o in referrers])
        #pprint(referrers)
        #input()
    return visited - extraids

def f():
    pass

class d:
    def __init__(self):
        pass

    def method(self):
        pass

    m2 = f

e = d()

f.e = e

def main():
    a1 = dict()
    a2 = dict()
    a3 = dict()
    a1['a2'] = a2
    a2['a3'] = a3
    a3['a1'] = a1
    b = dict()
    b['b'] = b
    c = dict()
    c['c'] = 'c'

    import gc
    import types
    print(len(
        _bfs([b],
            gc.get_referrers
            )
     ))

    sccs = tarjan([a1, b, c], gc.get_referrers)

    show_cycles(sccs, joined=True)
    print(sccs)
    del sccs
    gc.collect()


    sccs = tarjan([d, e, f])

    show_cycles(sccs, joined=True)

    return

    sccs = tarjan(gc.get_objects(), gc.get_referrers)
    print([len(i) for i in sccs])
    import objgraph
    objs = objgraph.at_addrs(sccs[0])
    print(objgraph.typestats(objs))

if __name__ == "__main__":
    main()
