from __future__ import print_function

from keras import activations, initializers
from keras import regularizers
from keras.engine import Layer
from keras.layers import Dropout
import theano.tensor
import tensorflow as tf
import keras.backend as K


class SpectralGraphConvolution(Layer):
    def __init__(self, output_dim,
                 init='glorot_uniform', activation='linear',
                 weights=None, W_regularizer=None,
                 b_regularizer=None, bias=True,
                 self_links=True, consecutive_links=True,
                 backward_links=True, edge_weighting=False, **kwargs):
        self.init = initializers.get(init)
        self.activation = activations.get(activation)
        self.output_dim = output_dim  # number of features per node

        self.self_links = self_links
        self.consecutive_links = consecutive_links
        self.backward_links = backward_links
        self.edge_weighting = edge_weighting

        self.W_regularizer = regularizers.get(W_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)

        self.bias = bias
        self.initial_weights = weights

        self.input_dim = None
        self.W = None
        self.b = None
        self.num_nodes = None
        self.num_features = None
        self.num_relations = None
        self.num_adjacency_matrices = None

        super(SpectralGraphConvolution, self).__init__(**kwargs)

    def compute_output_shape(self, input_shapes):
        features_shape = input_shapes[0]
        output_shape = (None, features_shape[1], self.output_dim)
        return output_shape

    def build(self, input_shapes):
        features_shape = input_shapes[0]
        assert len(features_shape) == 3
        self.input_dim = features_shape[1]
        self.num_nodes = features_shape[1]
        self.num_features = features_shape[2]
        self.num_relations = len(input_shapes) - 1

        self.num_adjacency_matrices = self.num_relations

        if self.consecutive_links:
            self.num_adjacency_matrices += 1

        if self.backward_links:
            self.num_adjacency_matrices *= 2

        if self.self_links:
            self.num_adjacency_matrices += 1

        self.W = []
        self.W_edges = []
        for i in range(self.num_adjacency_matrices):
            self.W.append(self.add_weight((self.num_features, self.output_dim),  # shape: (num_features, output_dim)
                                          initializer=self.init,
                                          name='{}_W_rel_{}'.format(
                                              self.name, i),
                                          regularizer=self.W_regularizer))

            if self.edge_weighting:
                self.W_edges.append(self.add_weight((self.input_dim, self.num_features),  # shape: (num_features, output_dim)
                                                    initializer='ones',
                                                    name='{}_W_edge_{}'.format(
                                                        self.name, i),
                                                    regularizer=self.W_regularizer))

        self.b = self.add_weight((self.input_dim, self.output_dim),
                                 initializer='random_uniform',
                                 name='{}_b'.format(self.name),
                                 regularizer=self.b_regularizer)

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        super(SpectralGraphConvolution, self).build(input_shapes)

    def call(self, inputs, mask=None):
        features = inputs[0]  # Shape: (None, num_nodes, num_features)
        A = inputs[1:]  # Shapes: (None, num_nodes, num_nodes)
        # print("A: ", A.shape)
        eye = A[0] * K.zeros(self.num_nodes, dtype='float32') + \
            K.eye(self.num_nodes, dtype='float32')

        # eye = K.eye(self.num_nodes, dtype='float32')

        if self.consecutive_links:
            shifted = tf.manip.roll(eye, shift=1, axis=0)
            A.append(shifted)

        if self.backward_links:
            for i in range(len(A)):
                A.append(K.permute_dimensions(A[i], [0, 2, 1]))

        if self.self_links:
            A.append(eye)

        AHWs = list()
        for i in range(self.num_adjacency_matrices):
            if self.edge_weighting:
                features *= self.W_edges[i]
            # Shape: (None, num_nodes, output_dim)
            HW = K.dot(features, self.W[i])
            # Shape: (None, num_nodes, num_features)
            AHW = K.batch_dot(A[i], HW)
            AHWs.append(AHW)
        # Shape: (None, num_supports, num_nodes, num_features)
        AHWs_stacked = K.stack(AHWs, axis=1)
        # Shape: (None, num_nodes, output_dim)
        output = K.max(AHWs_stacked, axis=1)

        if self.bias:
            output += self.b
        return self.activation(output)

    def get_config(self):
        config = {'output_dim': self.output_dim,
                  'init': "glorot_uniform",
                  'activation': "linear",
                  'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'num_bases': self.num_bases,
                  'bias': self.bias,
                  'input_dim': self.input_dim}
        base_config = super(SpectralGraphConvolution, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))
