# Define the model architectures here
import torch
from torch import nn

class VanillaWAP(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.watcher = None
        self.embedder = None
        self.positional_encoder = None
        self.parser = dict()
        self.config = config

        self.generate_watcher()
        self.generate_positional_encoder()
        self.generate_embedder()
        self.generate_parser()

    def forward(self, x):
        # CNN Feature Extraction
        x = self.watcher(x)

        # Positional Encoding
        x = x + self.positional_encoder
        x = torch.reshape(x, (x.shape[0], x.shape[1], 1, -1))
        # RNN Decoder

        y = 2 * torch.ones((x.shape[0], 1)).long()
        p = torch.zeros((x.shape[0], self.config['max_len'], self.config['vocab_size'] ))

        i = 0
        # While all y are not index = 3 and max length is not reached
        o_t, c_t, h_t = None, None, None
        while not torch.all(y == 3) and i < self.config['max_len']:

            # Embedding
            p_t, h_t, c_t, o_t = self.parse(x, y, c_t, h_t, o_t)
            p[:, i, :] = p_t.squeeze()
            y = torch.argmax(p_t.squeeze(), dim=1)

            # Next Iter
            i += 1

        return p
    def generate_watcher(self):
        """
        Generate the model based on the config
        :return: None
        """
        # Sequential model
        self.watcher = nn.Sequential()

        # Kernel Dimension of each layer
        layer_dims = [self.config['input_channels']] + self.config['num_features_map']
        for i in range(self.config['num_layers']):
            # Convolutional Layer
            self.watcher.add_module('conv{}'.format(i),
                                    nn.Conv2d(layer_dims[i], layer_dims[i+1],
                                            self.config['feature_kernel_size'][i],
                                            self.config['feature_kernel_stride'][i],
                                            self.config['feature_padding'][i]))

            # Batch Normalization if required
            if self.config['batch_norm'][i]:
                self.watcher.add_module('batchnorm{}'.format(i), nn.BatchNorm2d(layer_dims[i + 1]))

            # Activation Function
            self.watcher.add_module('relu{}'.format(i), nn.ReLU())

            # Max Pooling if required
            if self.config['feature_pooling_kernel_size'][i]:
                self.watcher.add_module('maxpool{}'.format(i),
                                        nn.MaxPool2d(self.config['feature_pooling_kernel_size'][i],
                                                   self.config['feature_pooling_stride'][i]))

        self.watcher.to(self.config['DEVICE'])

    def generate_positional_encoder(self):
        """
        Generate 2-D Positional Encoding as per https://arxiv.org/pdf/1908.11415.pdf
        :return:
        """
        x, y = torch.arange(self.config['output_dim'][0]), torch.arange(self.config['output_dim'][1])
        i, j = torch.arange(self.config['num_features_map'][-1] // 4), torch.arange(self.config['num_features_map'][-1] // 4)
        D = self.config['num_features_map'][-1]

        pe = torch.zeros((D, self.config['output_dim'][0], self.config['output_dim'][1]))

        x_i = torch.einsum("i, j, k -> ijk", 10000 ** (4 * i / D), x, torch.ones_like(y))
        y_i = torch.einsum("i, j, k -> ijk", 10000 ** (4 * j / D), torch.ones_like(x), y)

        x, y = x.unsqueeze(1), y.unsqueeze(0)
        i, j = i.unsqueeze(-1).unsqueeze(-1), j.unsqueeze(-1).unsqueeze(-1)

        pe[2 * i, x, y]              = torch.sin(x_i)
        pe[2 * i + 1, x, y]          = torch.cos(x_i)
        pe[2 * j + D // 2, x, y]     = torch.sin(y_i)
        pe[2 * j + 1 + D // 2, x, y] = torch.cos(y_i)

        self.positional_encoder = pe

    def generate_embedder(self):
        """
        Generates the embedder
        :return:
        """
        self.embedder = nn.Embedding(self.config['vocab_size'], self.config['embedding_dim'], padding_idx=0)

    def generate_parser(self):
        """
        Generates the parser
        :return:
        """

        self.parser['lstm'] = nn.LSTM(self.config['embedding_dim'] + self.config['hidden_dim'],
                                       self.config['hidden_dim'], batch_first=True)

        # Define linear layers to compute the initial hidden and cell states of the forward and reverse LSTMs
        D = self.config['num_features_map'][-1]
        self.parser['W_h'] = nn.Linear(D, self.config['hidden_dim'])
        self.parser['W_c'] = nn.Linear(D, self.config['cell_dim'])

        # Define linear layers to project the hidden state and memory vector to get the attention weights
        L = self.config['output_dim'][0] * self.config['output_dim'][1]
        self.parser['W_1'] = nn.Linear(self.config['hidden_dim'], L)
        self.parser['W_2'] = nn.Linear(D, 1)

        # Define Linear Layer to combine Hidden State and Context
        self.parser['W_3'] = nn.Linear(self.config['hidden_dim'] + D, self.config['cell_dim'], bias=False)

        # Define Linear Layer to Project the Cell State to the Output Vocabulary
        self.parser['W_4'] = nn.Linear(self.config['cell_dim'], self.config['vocab_size'], bias=False)

    def parse(self, x, y, h_t_1=None, c_t_1=None, o_t_1=None):
        """
        x is of shape (batch_size, num_features_map[-1], 1, output_dim[0]*output_dim[1]) - (B, D, 1, L)
        y is of shape (batch_size, vocab) - (B, V)
        h_t_1 is of shape (batch_size, hidden_dim) - (B, H)
        c_t_1 is of shape (batch_size, cell_dim) - (B, C)
        o_t_1 is of shape (batch_size, hidden_dim) - (B, H)
        """

        # Compute the initial hidden and cell states of the forward and reverse LSTMs
        if h_t_1 is None:
            h_t_1 = torch.tanh(self.parser['W_h'](torch.mean(x, dim=-1).squeeze())).unsqueeze(0)
            c_t_1 = torch.tanh(self.parser['W_c'](torch.mean(x, dim=-1).squeeze())).unsqueeze(0)
            o_t_1 = torch.zeros((x.shape[0], self.config['hidden_dim'])).to(self.config['DEVICE'])

        w_t_1 = self.embedder(y).squeeze()

        # Compute the hidden and cell states of the forward and reverse LSTMs
        input_t_1 = torch.concat([w_t_1, o_t_1], dim=-1).unsqueeze(1)
        _, (h_t, c_t) = self.parser['lstm'](input_t_1, (h_t_1, c_t_1))

        # Compute the attention weights
        input_t_11 = self.parser['W_1'](h_t)
        input_t_12 = self.parser['W_2'](x.view(x.shape[0], x.shape[3], x.shape[2], x.shape[1])).squeeze()
        a_t = torch.tanh( input_t_11 + input_t_12)
        alpha_t = torch.softmax(a_t, dim=-1)

        # Compute the context vector
        ctx_t = torch.einsum("ijkl, kil -> kij", x, alpha_t)
        o_t = torch.tanh(self.parser['W_3'](torch.concat([h_t, ctx_t], dim=-1))).squeeze()

        # Compute the output vector
        p_t = torch.softmax(self.parser['W_4'](o_t), dim=-1)

        return p_t, h_t, c_t, o_t

    def predict(self):
        pass

    def save(self):
        pass

    def load(self):
        pass
