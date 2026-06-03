
import numpy as np
import itertools
from scipy.interpolate import  griddata, splprep, splev
from matplotlib import pyplot as plt
from scipy.spatial import Delaunay

def _make_transform(use_log):
    if use_log:
        def f(a):
            a = np.asarray(a, dtype=float)
            if np.any(a <= 0):
                raise ValueError("Log transform requested but data contains non-positive values.")
            return np.log10(a)
        def finv(a):
            return np.power(10.0, a)
        return f, finv
    else:
        return (lambda a: np.asarray(a, dtype=float),
                lambda a: np.asarray(a, dtype=float))

def _robust_scale(a):
    # Robust centering/scaling for triangulation stability
    med = np.nanmedian(a)
    q16, q84 = np.nanpercentile(a, [16, 84])
    s = q84 - q16
    if not np.isfinite(s) or s == 0:
        s = np.nanstd(a)
    if not np.isfinite(s) or s == 0:
        s = 1.0
    return (a - med) / s

def _edge_intersection(p1, p2, v1, v2, level, eps=1e-15):
    dv1 = v1 - level
    dv2 = v2 - level

    # Edge entirely on level -> ambiguous (skip to avoid duplicates)
    if abs(dv1) < eps and abs(dv2) < eps:
        return None

    # No crossing
    if dv1 * dv2 > 0:
        return None

    # One endpoint on level
    if abs(dv1) < eps:
        return p1
    if abs(dv2) < eps:
        return p2

    # Linear interpolation along edge
    t = (level - v1) / (v2 - v1)
    return p1 + t * (p2 - p1)

def _key(pt, tol):
    return tuple(np.round(pt / tol).astype(np.int64))

def _stitch_segments(segments_t, segments_xy, tol_t=1e-10):
    # segments_* are lists of shape (2, 2): [ [x0,y0], [x1,y1] ]
    if len(segments_t) == 0:
        return []

    seg_t = [np.asarray(s, dtype=float) for s in segments_t]
    seg_xy = [np.asarray(s, dtype=float) for s in segments_xy]

    endpoint_map = {}
    for i, s in enumerate(seg_t):
        k0 = _key(s[0], tol_t)
        k1 = _key(s[1], tol_t)
        endpoint_map.setdefault(k0, []).append((i, 0))
        endpoint_map.setdefault(k1, []).append((i, 1))

    unused = set(range(len(seg_t)))
    curves = []

    while unused:
        i0 = unused.pop()

        poly_t = [seg_t[i0][0], seg_t[i0][1]]
        poly_xy = [seg_xy[i0][0], seg_xy[i0][1]]

        def extend(at_front):
            while True:
                cur_t = poly_t[0] if at_front else poly_t[-1]
                k = _key(cur_t, tol_t)
                candidates = endpoint_map.get(k, [])

                next_seg = None
                next_end = None
                for (j, end_idx) in candidates:
                    if j in unused:
                        next_seg = j
                        next_end = end_idx
                        break

                if next_seg is None:
                    return

                if next_end is None:
                    return

                unused.remove(next_seg)

                # If matched endpoint is 0, opposite is 1; if matched is 1, opposite is 0
                opp = 1 - next_end
                p_t = seg_t[next_seg][opp]
                p_xy = seg_xy[next_seg][opp]

                if at_front:
                    poly_t.insert(0, p_t)
                    poly_xy.insert(0, p_xy)
                else:
                    poly_t.append(p_t)
                    poly_xy.append(p_xy)

        extend(at_front=False)
        extend(at_front=True)

        # Drop duplicate consecutive points if any
        clean = [poly_xy[0]]
        for p in poly_xy[1:]:
            if np.linalg.norm(p - clean[-1]) > 0:
                clean.append(p)

        curves.append(np.asarray(clean))

    return curves

def _resample_curve_spline(curve, k=1, smoothing=0.0, points_factor=1.0, tol=1e-14):
    """
    Resample a polyline with a parametric spline.

    Args:
        curve: array of shape (N, 2)
        k: spline order (1=linear, 2=quadratic)
        smoothing: scipy splprep smoothing parameter s
        points_factor: output density multiplier relative to input points
    """
    curve = np.asarray(curve, dtype=float)
    if curve.ndim != 2 or curve.shape[1] != 2 or curve.shape[0] < 2:
        return curve

    # Remove duplicate consecutive points to avoid spline singularities.
    clean = [curve[0]]
    for p in curve[1:]:
        if np.linalg.norm(p - clean[-1]) > tol:
            clean.append(p)
    curve = np.asarray(clean, dtype=float)

    if curve.shape[0] < 2:
        return curve

    closed = np.linalg.norm(curve[0] - curve[-1]) <= tol
    if closed and curve.shape[0] > 2:
        # splprep(per=True) handles closure internally; avoid duplicate end point.
        curve = curve[:-1]

    n = curve.shape[0]
    if n < 2:
        return curve

    k = int(max(1, k))
    k = min(k, n - 1)

    n_out = int(np.ceil(max(2.0, n * max(1.0, float(points_factor)))))
    n_out = max(n_out, n)

    try:
        tck, _ = splprep(
            [curve[:, 0], curve[:, 1]],
            s=float(max(0.0, smoothing)),
            k=k,
            per=bool(closed)
        )
        u_new = np.linspace(0.0, 1.0, n_out, endpoint=not closed)
        x_new, y_new = splev(u_new, tck)
        out = np.column_stack([x_new, y_new])
        if closed:
            out = np.vstack([out, out[0]])
        return out
    except Exception:
        # If spline fitting fails (degenerate geometry), keep original contour.
        return curve

def iso_contours_unstructured(
    x, y, z, z0,
    logx=False, logy=False, logz=False,
    qhull_options="Qbb Qc Qz Q12",
    tol_t=1e-10,
    interpolation="linear",
    smoothing=0.0,
    points_factor=1.0
):
    """
    Extract contour curve(s) z=z0 from unstructured (x,y,z) points.

        Optional post-processing can improve visual smoothness:
            - interpolation="quadratic": resample each contour with quadratic splines
            - smoothing>0: spline smoothing parameter passed to scipy splprep
            - points_factor>1: denser sampling along the contour

    Returns:
        list of arrays, each with shape (Ni, 2), in original (x,y) coordinates.
        Multiple disconnected contours are returned as multiple arrays.
    """
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()

    if not (x.size == y.size == z.size):
        raise ValueError("x, y, z must have same length.")

    finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z = x[finite], y[finite], z[finite]

    if x.size < 3:
        return []

    fx, fx_inv = _make_transform(logx)
    fy, fy_inv = _make_transform(logy)
    fz, _ = _make_transform(logz)

    xt = fx(x)
    yt = fy(y)
    zt = fz(z)
    z0t = fz(np.array([z0], dtype=float))[0]

    # Remove duplicate points in transformed (x,y), keeping first occurrence
    pts_t = np.column_stack([xt, yt])
    uniq, uniq_idx = np.unique(pts_t, axis=0, return_index=True)
    xt, yt, zt = xt[uniq_idx], yt[uniq_idx], zt[uniq_idx]
    pts_t = np.column_stack([xt, yt])

    if pts_t.shape[0] < 3:
        return []

    # Robust scaling only for triangulation
    xts = _robust_scale(xt)
    yts = _robust_scale(yt)
    pts_scaled = np.column_stack([xts, yts])

    tri = Delaunay(pts_scaled, qhull_options=qhull_options)

    segments_t = []
    segments_xy = []

    edges = [(0, 1), (1, 2), (2, 0)]

    for simp in tri.simplices:
        p_t = pts_t[simp]            # transformed x,y (for geometric interpolation)
        v = zt[simp]                 # transformed z

        vmin, vmax = np.min(v), np.max(v)
        if not (vmin <= z0t <= vmax):
            continue

        inter_t = []
        for i, j in edges:
            pt = _edge_intersection(p_t[i], p_t[j], v[i], v[j], z0t)
            if pt is not None:
                inter_t.append(pt)

        if len(inter_t) < 2:
            continue

        # Deduplicate possible repeated intersections
        uniq_pts = []
        for p in inter_t:
            if not any(np.linalg.norm(p - q) <= tol_t for q in uniq_pts):
                uniq_pts.append(p)

        if len(uniq_pts) != 2:
            continue

        a_t, b_t = np.asarray(uniq_pts[0]), np.asarray(uniq_pts[1])
        a_xy = np.array([fx_inv(a_t[0]), fy_inv(a_t[1])], dtype=float)
        b_xy = np.array([fx_inv(b_t[0]), fy_inv(b_t[1])], dtype=float)

        segments_t.append(np.vstack([a_t, b_t]))
        segments_xy.append(np.vstack([a_xy, b_xy]))

    curves = _stitch_segments(segments_t, segments_xy, tol_t=tol_t)

    interp = str(interpolation).lower()
    if interp not in ("linear", "quadratic"):
        raise ValueError("interpolation must be 'linear' or 'quadratic'.")

    if smoothing < 0:
        raise ValueError("smoothing must be >= 0.")

    k = 1 if interp == "linear" else 2
    if (k > 1) or (smoothing > 0) or (points_factor > 1):
        curves = [
            _resample_curve_spline(
                c,
                k=k,
                smoothing=smoothing,
                points_factor=points_factor,
                tol=tol_t
            )
            for c in curves
        ]

    return curves

def interpolateData(x,y,z,nx=200,ny=200,method='linear',fill_value=np.nan,xnew=None,ynew=None):

    if x.min() == x.max() or y.min() == y.max(): # Can not interpolate
        return None,None,None
    elif xnew is None or ynew is None:
        xnew = np.linspace(x.min(),x.max(),nx)
        ynew = np.linspace(y.min(),y.max(),ny)

    xi = np.array([list(v) for v in itertools.product(xnew,ynew)])
    znew = griddata(list(zip(x,y)),z,xi=xi, 
                    method=method,fill_value=fill_value)
    znew = np.reshape(znew,(len(xnew),len(ynew)))
    xnew,ynew  = np.meshgrid(xnew,ynew,indexing='ij')

    return xnew,ynew,znew

def getContours(x,y,z,contourValues,npathmax=1):
    

    contours = plt.contour(x, y, z, contourValues)
    plt.close()

    contoursDict = {}

    for i,item in enumerate(contours.collections):
        cV = contourValues[i]
        xData = []
        yData = []
        for ipath,p in enumerate(item.get_paths()):
            if ipath >= npathmax:
                continue
            v = p.vertices
            xData += list(v[:, 0])
            yData += list(v[:, 1])
        if len(xData) == 0:
            continue
        contoursDict[cV] = np.array(list(zip(xData,yData)))
    
    return contoursDict

def saveContours(contoursDict,fname,header):

    with open(fname,'w') as f:
        for cV,data in contoursDict.items():
            np.savetxt(f,data,fmt='%.4e',delimiter=',',header=header,comments='\n\n# Contour value=%1.2f \n' %cV)
    print('Contours saved to %s' %fname)

def readContours(fname):

    contoursDict = {}
    with open(fname,'r') as f:
        dataBlocks = f.read().split('#')[1:]
        for data in dataBlocks: 
            data = data.splitlines()
            cV = eval(data[0].split('=')[1])
            dataPts = np.genfromtxt(data,delimiter=',',names=True,skip_header=1)
            contoursDict[cV] = dataPts

    return contoursDict

def label_line(fig,line, label_text, 
               near_i=None, near_x=None, near_y=None, 
               rotation_offset=0, offset=(0,0),fontsize=13,
               xmin=None,rotation=None,boxalpha=1.0):
    """call 
        l, = plt.loglog(x, y)
        label_line(l, "text", near_x=0.32)
    """
    def put_label(i):
        """put label at given index"""
        i = min(i, len(x)-2)
        dx = sx[i+1] - sx[i]
        dy = sy[i+1] - sy[i]
        if rotation is None:
            rot = np.rad2deg(np.arctan2(dy, dx)) + rotation_offset
        else:
            rot = rotation
        pos = [(x[i] + x[i+1])/2. + offset[0], (y[i] + y[i+1])/2 + offset[1]]
        if pos[0] > xmin:
            plt.text(pos[0], pos[1], label_text, size=fontsize, 
                     rotation=rot, color = line.get_color(),
                     ha="center", va="center", bbox = dict(ec='1',fc='1',alpha=boxalpha))

    x = line.get_xdata()
    y = line.get_ydata()
    ax = fig.get_axes()[0]
    if ax.get_xscale() == 'log':
        sx = np.log10(x)    # screen space
    else:
        sx = x
    if ax.get_yscale() == 'log':
        sy = np.log10(y)
    else:
        sy = y

    # find index
    if near_i is not None:
        i = near_i
        if i < 0: # sanitize negative i
            i = len(x) + i
        put_label(i)
    elif near_x is not None:
        for i in range(len(x)-2):
            if (x[i] < near_x and x[i+1] >= near_x) or (x[i+1] < near_x and x[i] >= near_x):
                put_label(i)
    elif near_y is not None:
        for i in range(len(y)-2):
            if (y[i] < near_y and y[i+1] >= near_y) or (y[i+1] < near_y and y[i] >= near_y):
                put_label(i)
    else:
        raise ValueError("Need one of near_i, near_x, near_y")
