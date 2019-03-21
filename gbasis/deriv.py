"""Derivative of a Gaussian Contraction."""
import numpy as np
from scipy.special import comb, perm


# TODO: in the case of generalized Cartesian contraction where multiple shells have the same sets of
# exponents but different sets of primitive coefficients, it will be helpful to vectorize the
# `prim_coeffs` also.
# FIXME: name is pretty bad
# TODO: vectorize for multiple orders? Caching instead?
def _eval_deriv_contractions(coords, orders, center, angmom_comps, alphas, prim_coeffs, norm):
    """Return the evaluation of the derivative of a Cartesian contraction.

    Parameters
    ----------
    coords : np.ndarray(N, 3)
        Point in space where the derivative of the Gaussian primitive is evaluated.
        Coordinates must be given as a two dimensional array, even if one coordinate is given.
    orders : np.ndarray(3,)
        Orders of the derivative.
        Negative orders are treated as zero orders.
    center : np.ndarray(3,)
        Center of the Gaussian primitive.
    angmom_comps : np.ndarray(L, 3)
        Component of the angular momentum that corresponds to this dimension.
        Angular momentum components must be given as a two dimensional array, even if only one
        is given.
    alphas : np.ndarray(K,)
        Values of the (square root of the) precisions of the primitives.
    prim_coeffs : np.ndarray(K,)
        Contraction coefficients of the primitives.
    norm : np.ndarray(L, K)
        Normalization constants for the primitives in each contraction.

    Returns
    -------
    derivative : np.ndarray(L, N)
        Evaluation of the derivative at each given coordinate.

    Notes
    -----
    The input is not checked. This means that you must provide the parameters as they are specified
    in the docstring. They must all be numpy arrays with the **correct shape**.

    """
    # pylint: disable=R0914
    # NOTE: following convention will be used to organize the axis of the multidimensional arrays
    # axis 0 = index for term in hermite polynomial (size: min(K, n)) where n is the order in given
    # dimension
    # axis 1 = index for primitive (size: K)
    # axis 2 = index for dimension (x, y, z) of coordinate (size: 3)
    # axis 3 = index for angular momentum vector (size: L)
    # axis 4 = index for coordinate (out of a grid) (size: N)
    # adjust the axis
    coords = coords.T[np.newaxis, np.newaxis, :, np.newaxis, :]
    # NOTE: if `coord` is two dimensional (3, N), then coords has shape (1, 1, 3, 1, N). If it is
    # one dimensional (3,), then coords has shape (1, 1, 3, 1)
    # NOTE: `order` is still assumed to be a one dimensional
    center = center[np.newaxis, np.newaxis, :, np.newaxis, np.newaxis]
    angmom_comps = angmom_comps.T[np.newaxis, np.newaxis, :, :, np.newaxis]
    # NOTE: if `angmom_comps` is two-dimensional (3, L), has shape (1, 1, 3, L). If it is one
    # dimensional (3, ) then it has shape (1, 1, 3)
    alphas = alphas[np.newaxis, :, np.newaxis, np.newaxis, np.newaxis]
    # NOTE: `prim_coeffs` will be used as a 1D array

    # useful variables
    rel_coords = coords - center
    gauss = np.exp(-alphas * rel_coords ** 2)

    # zeroth order (i.e. no derivatization)
    indices_noderiv = orders <= 0
    zero_rel_coords, zero_angmom_comps, zero_gauss = (
        rel_coords[:, :, indices_noderiv],
        angmom_comps[:, :, indices_noderiv],
        gauss[:, :, indices_noderiv],
    )
    zeroth_part = np.prod(zero_rel_coords ** zero_angmom_comps * zero_gauss, axis=(0, 2))
    # NOTE: `zeroth_part` now has axis 0 for primitives, axis 1 for angular momentum vector, and
    # axis 2 for coordinate

    deriv_part = 1
    nonzero_rel_coords, nonzero_orders, nonzero_angmom_comps, nonzero_gauss = (
        rel_coords[:, :, ~indices_noderiv],
        orders[~indices_noderiv],
        angmom_comps[:, :, ~indices_noderiv],
        gauss[:, :, ~indices_noderiv],
    )
    nonzero_orders = nonzero_orders[np.newaxis, np.newaxis, :, np.newaxis, np.newaxis]

    # derivatization part
    if nonzero_orders.size != 0:
        # General approach: compute the whole coefficents, zero out the irrelevant parts
        # NOTE: The following step assumes that there is only one set (nx, ny, nz) of derivatization
        # orders i.e. we assume that only one axis (axis 2) of `nonzero_orders` has a dimension
        # greater than 1
        indices_herm = np.arange(np.max(nonzero_orders) + 1)[:, None, None, None, None]
        # get indices that are used as powers of the appropriate terms in the derivative
        # NOTE: the negative indices must be turned into zeros (even though they are turned into
        # zeros later anyways) because these terms are sometimes zeros (and negative power is
        # undefined).
        indices_angmom = nonzero_angmom_comps - nonzero_orders + indices_herm
        indices_angmom[indices_angmom < 0] = 0
        # get coefficients for all entries
        coeffs = (
            comb(nonzero_orders, indices_herm)
            * perm(nonzero_angmom_comps, nonzero_orders - indices_herm)
            * (-alphas ** 0.5) ** indices_herm
            * nonzero_rel_coords ** indices_angmom
        )
        # zero out the appropriate terms
        indices_zero = np.where(indices_herm < np.maximum(0, nonzero_orders - nonzero_angmom_comps))
        coeffs[indices_zero[0], :, indices_zero[2], indices_zero[3]] = 0
        indices_zero = np.where(nonzero_orders < indices_herm)
        coeffs[indices_zero[0], :, indices_zero[2]] = 0
        # compute
        # FIXME: I can't seem to vectorize the next part due to the API of
        # np.polynomial.hermite.hermval. The main problem is that the indices for the primitives and
        # the dimension must be constrained for the given `x` and `c`, otherwise the hermitian
        # polynomial is evaluated at many unnecessary points.
        hermite = np.prod(
            [
                [
                    [
                        np.polynomial.hermite.hermval(
                            alphas[:, i, 0, 0, 0] ** 0.5 * nonzero_rel_coords[:, 0, k, 0, l],
                            coeffs[:, i, k, :, l],
                        )
                        for k in range(nonzero_rel_coords.shape[2])
                    ]
                    for l in range(coords.shape[4])
                ]
                for i in range(alphas.shape[1])
            ],
            # NOTE: for loop over the axis 1 (primitives), 3 (angular momentum vector), 4
            # (coordinate), and 2 (dimension) moves it to axis 0, 1, 2, and 3, respectively, while
            # removing these indices from alphas and coeffs. hermval returns an array of c.shape[1:]
            # + x.shape.
            # Therefore, axis 0 is the index for primitive
            #            axis 1 is the index for coordinates
            #            axis 2 is for index for dimension (x, y, z)
            #            axis 3 is the index for angular momentum vector
            #            axis 4 is the index for term in hermite polynomial
            axis=(2, 4),
        )
        # swap axis 1 and 2
        hermite = np.swapaxes(hermite, 1, 2)
        # NOTE: `hermite` now has axis 0 for primitives, 1 for angular momentum vector, and axis 2
        # for coordinates
        deriv_part = np.prod(nonzero_gauss, axis=(0, 2)) * hermite

    norm = norm.T[:, :, np.newaxis]
    return np.tensordot(prim_coeffs, norm * zeroth_part * deriv_part, (0, 0))


def eval_deriv_shell(*, coords, orders, shell):
    """Return the derivatives of a set of Cartesian contractions evaluated at the given coordinates.

    Parameters
    ----------
    coords : np.ndarray(N, 3)
        Point in space where the derivative of the Gaussian primitive is evaluated.
    orders : np.ndarray(3,)
        Orders of the derivative.
        Negative orders are treated as zero orders.
    shell : ContractedCartesianGaussians
        Set of contracted Cartesian Gaussians with the same angular momentum.

    Returns
    -------
    derivative : np.ndarray(L, N)
        Evaluation of the derivative.
        :math:`L` is the number of contractions associated with the given `shell`.

    Raises
    ------
    TypeError
        If the arguments are given as positional arguments.

    Notes
    -----
    When calling this function, the arguments must be given via keywords and not positional
    arguments. This feature is used to catch problems that arise due to a change in API.

    """
    alphas = shell.exps
    prim_coeffs = shell.coeffs
    angmom_comps = shell.angmom_components
    center = shell.coord
    norm = shell.norm
    return _eval_deriv_contractions(coords, orders, center, angmom_comps, alphas, prim_coeffs, norm)


def eval_shell(*, coords, shell):
    """Return the a set of Cartesian contractions evaluated at the given coordinates.

    Parameters
    ----------
    coords : np.ndarray(N, 3)
        Point in space where the derivative of the Gaussian primitive is evaluated.
    shell : ContractedCartesianGaussians
        Set of contracted Cartesian Gaussians with the same angular momentum.

    Returns
    -------
    derivative : np.ndarray(L, N)
        Evaluation of the derivative.
        :math:`L` is the number of contractions associated with the given `shell`.

    Raises
    ------
    TypeError
        If the arguments are given as positional arguments.

    Notes
    -----
    When calling this function, the arguments must be given via keywords and not positional
    arguments. This feature is used to catch problems that arise due to a change in API.

    """
    return eval_deriv_shell(coords=coords, orders=np.zeros(shell.coord.shape), shell=shell)  # nosec
