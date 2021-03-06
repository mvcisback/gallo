import itertools as itr
import time

import numpy as np
import scipy.sparse as sps
import scipy.sparse.linalg as linalg
import matplotlib.tri as tri

from gallo.formulations.diffusion import Diffusion
from gallo.formulations.nda import NDA
from gallo.formulations.saaf import SAAF
from gallo.upscatter_acceleration import UA

class Solver():
    def __init__(self, operator):
        self.op = operator
        self.ua_bool = False
        if isinstance(self.op, NDA):
            self.ho_op = SAAF(self.op.fegrid, self.op.mat_data)
        self.mat_data = self.op.mat_data
        self.num_groups = self.op.num_groups
        self.num_nodes = self.op.num_nodes
        self.num_elts = self.op.num_elts
        self.num_mats = self.mat_data.get_num_mats()
        self.num_angs = self.op.fegrid.num_angs
        self.angs = self.op.fegrid.angs
        self.weights = self.op.fegrid.weights

    def get_ang_flux(self, group_id, source, ang, angle_id, phi_prev):
        lhs = self.op.make_lhs(ang, group_id).tocsr()
        rhs = self.op.make_rhs(group_id, source, ang, angle_id, phi_prev)
        ang_flux = linalg.cg(lhs, rhs)[0]
        #ang_flux = linalg.spsolve(lhs, rhs)
        return ang_flux

    def get_scalar_flux(self, group_id, source, phi_prev, ho_sols=None):
        scalar_flux = 0
        if isinstance(self.op, Diffusion) or isinstance(self.op, NDA):
            lhs = self.op.make_lhs(group_id, ho_sols=ho_sols).tocsr()
            rhs = self.op.make_rhs(group_id, source, phi_prev)
            scalar_flux = linalg.cg(lhs, rhs)[0]
            #scalar_flux = linalg.spsolve(lhs, rhs)
            return scalar_flux
        else:
            ang_fluxes = np.zeros((4, self.num_nodes))
            # Iterate over all angle possibilities
            for i, ang in enumerate(self.angs):
                ang = np.array(ang)
                ang_fluxes[i] = self.get_ang_flux(group_id, source, ang, i, phi_prev)
                scalar_flux += self.weights[i] * ang_fluxes[i]
            return scalar_flux, ang_fluxes

    def solve_in_group(self, source, group_id, phi_prev, max_iter=1000,
                       tol=1e-6, verbose=True):
        num_mats = self.mat_data.get_num_mats()
        for mat in range(num_mats):
            scatmat = self.mat_data.get_sigs(mat)
            if np.count_nonzero(scatmat) == 0:
                scattering = False
            else:
                scattering = True
        if self.num_groups > 1 and verbose:
            print("Starting Group ", group_id)
        if isinstance(self.op, NDA):
            # Run preliminary solve on low-order system
            ho_sols = 0
            phi_prev[group_id] = self.get_scalar_flux(group_id, source, phi_prev, ho_sols=ho_sols)
        for i in range(max_iter):
            if scattering and verbose:
                print("Within-Group Iteration: ", i)
            if isinstance(self.op, NDA):
                ho_solver = Solver(self.ho_op)
                ho_phis, ho_psis = ho_solver.get_scalar_flux(group_id, source, phi_prev)
                ho_sols = [ho_phis, ho_psis]
                phi = self.get_scalar_flux(group_id, source, phi_prev, ho_sols=ho_sols)
            elif isinstance(self.op, Diffusion):
                phi = self.get_scalar_flux(group_id, source, phi_prev)
            else:
                phi, ang_fluxes = self.get_scalar_flux(group_id, source, phi_prev)
            if not scattering:
                break
            norm = np.linalg.norm(phi - phi_prev[group_id], float('inf'))/np.linalg.norm(phi, float('inf'))
            if verbose: print("Norm: ", norm)
            if norm < tol:
                break
            phi_prev[group_id] = np.copy(phi)
        if i == max_iter:
            print("Warning: maximum number of iterations reached in solver")
        if self.num_groups > 1 and verbose:
            print("Finished Group ", group_id)
        if scattering and verbose:
            print("Number of Within-Group Iterations: ", i + 1)
            print("Final Phi Norm: ", norm)
        if isinstance(self.op, Diffusion):
            return phi
        elif isinstance(self.op, NDA):
            return phi, ho_sols
        else:
            return phi, ang_fluxes

    def solve_outer(self, source, verbose=True, max_iter=50, tol=1e-5):
        phis = np.ones((self.num_groups, self.num_nodes))
        ang_fluxes = np.zeros((self.num_groups, 4, self.num_nodes))
        for it_count in range(max_iter):
            if self.num_groups != 1 and verbose:
                print("Gauss-Seidel Iteration: ", it_count)
            phis_prev = np.copy(phis)
            if isinstance(self.op, NDA):
                all_ho_sols = []
            for g in range(self.num_groups):
                if isinstance(self.op, Diffusion):
                    phi = self.solve_in_group(source, g, phis, verbose=verbose)
                    phis[g] = phi
                elif isinstance(self.op, NDA):
                    phi, ho_sols = self.solve_in_group(source, g, phis, verbose=verbose)
                    phis[g] = phi
                    all_ho_sols.append(ho_sols)
                else:
                    phi, psi = self.solve_in_group(source, g, phis)
                    phis[g] = phi
                    ang_fluxes[g] = psi
            if self.num_groups == 1:
                break
            else:
                if self.ua_bool:
                    # Calculate Correction Term
                    print("Calculating Upscatter Acceleration Term")
                    upscatter_accelerator = UA(self.op)
                    # Calculate eigenfunctions
                    eig_for_mat = np.zeros((self.num_mats, self.num_groups))
                    for midx in range(self.num_mats):
                        eig_for_mat[midx] = upscatter_accelerator.compute_eigenfunction(midx)
                    eigs = np.zeros((self.num_groups, self.num_nodes))
                    for g in range(self.num_groups):
                        for elt in range(self.num_elts):
                            e = self.op.fegrid.element(elt)
                            midx = e.mat_id
                            for n in range(3):
                                n_global = self.op.fegrid.node(elt, n)
                                nid = n_global.id
                                eigs[g, nid] += eig_for_mat[midx, g]*1/3
                    epsilon = upscatter_accelerator.calculate_correction(phis, phis_prev, all_ho_sols)
                    phis += epsilon*eigs
                res = np.linalg.norm(phis - phis_prev, float('inf'))/np.linalg.norm(phis, float('inf'))
                if verbose:
                    print("GS Norm: ", res)
            if res < tol:
                break
        if isinstance(self.op, Diffusion) or isinstance(self.op, NDA):
            return phis
        else:
            return phis, ang_fluxes

    def solve(self, source, ua_bool=False):
        start = time.time()
        if ua_bool:
            self.ua_bool = True
        if isinstance(self.op, Diffusion) or isinstance(self.op, NDA):
            phis = self.solve_outer(source)
            end = time.time()
            print("Runtime:", np.round(end - start, 5), "seconds")
            return phis
        else:
            phis, ang_fluxes = self.solve_outer(source)
            end = time.time()
            print("Runtime:", np.round(end - start, 5), "seconds")
            return phis, ang_fluxes
