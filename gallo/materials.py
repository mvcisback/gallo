import os
import numpy as np


class Materials():
    def __init__(self, filename):
        """Constructor of materials object. Stores material data for all
        materials """

        # Verify file exists
        assert os.path.exists(filename), "Material file: " + filename\
            + " does not exist"
        with open(filename) as fp:
            line = fp.readline()
            mats_groups = line.split("|")
            self.num_mats = int(mats_groups[0])
            self.num_groups = int(mats_groups[1])
            self.names = []
            self.sig_t = np.zeros((self.num_mats, self.num_groups))
            self.sig_a = np.zeros((self.num_mats, self.num_groups))
            self.sig_s = np.zeros((self.num_mats, self.num_groups,
                                   self.num_groups))
            self.sig_f = np.zeros((self.num_mats, self.num_groups))
            self.D = np.zeros((self.num_mats, self.num_groups))
            self.nu = np.zeros((self.num_mats, self.num_groups))
            self.inv_sigt = np.zeros((self.num_mats, self.num_groups))
            self.chi = np.zeros((self.num_mats, self.num_groups))
            for i in range(self.num_mats):
                line = fp.readline()
                attributes = line.split("|")
                self.names.append(attributes[2].strip())
                for j in range(self.num_groups):
                    self.sig_a[i, j] = float(attributes[4])
                    scat = np.array(attributes[5].split())
                    self.sig_s[i, j, :] = scat.astype(float)
                    self.sig_t[i, j] = self.sig_a[i, j] + np.sum(self.sig_s[i, j, :])
                    self.sig_f[i, j] = float(attributes[6])
                    self.nu[i, j] = float(attributes[7])
                    self.chi[i, j] = float(attributes[8])

                    # Derived quantities
                    self.D[i, j] = 1 / (3 * self.sig_t[i, j])
                    self.inv_sigt[i, j] = 1 / self.sig_t[i, j]
                    if j == (self.num_groups - 1):
                        continue
                    else:
                        line = fp.readline()
                        attributes = line.split("|")

    def get_name(self, mat_id):
        return self.names[mat_id]

    def get_num_mats(self):
        return self.num_mats

    def get_num_groups(self):
        return self.num_groups

    def get_sigt(self, mat_id, group_id):
        return self.sig_t[mat_id, group_id]

    def get_siga(self, mat_id, group_id):
        return self.sig_a[mat_id, group_id]

    def get_sigs(self, mat_id):
        return self.sig_s[mat_id]

    def get_sigf(self, mat_id, group_id):
        return self.sig_f[mat_id, group_id]

    def get_chi(self, mat_id, group_id):
        return self.chi[mat_id, group_id]

    def get_all_chi(self):
        return np.array([self.chi[0]]).transpose()

    def get_diff(self, mat_id, group_id):
        return self.D[mat_id, group_id]

    def get_nu(self, mat_id, group_id):
        return self.nu[mat_id, group_id]

    def get_inv_sigt(self, mat_id, group_id):
        return self.inv_sigt[mat_id, group_id]

    def get_sigr(self, mat_id, group_id):
        scatmat = self.get_sigs(mat_id)
        sigt = self.get_sigt(mat_id, group_id)
        sigr = sigt - scatmat[group_id, group_id]
        return sigr
