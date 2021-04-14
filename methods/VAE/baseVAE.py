import tensorflow as tf

class BaseVAE(tf.keras.Model):

  """Abstract base class of a VAE model."""
  def __init__(self, latent_dim, encoder_fn, decoder_fn, loss_fn, input_shape, **kwargs):
    super(BaseVAE, self).__init__(**kwargs)
    self.latent_dim   = latent_dim
    self.encoder      = encoder_fn(input_shape, latent_dim)
    self.decoder      = decoder_fn(input_shape, latent_dim)
    self.loss_fn      = loss_fn
    self.metric_names = ["loss", "reconstruction_loss", "elbo"]
    self.metrics_dict = {name:tf.keras.metrics.Mean(name=name) for name in self.metric_names}


  @property
  def metrics(self):
      return [self.metrics_dict[name] for name in self.metric_names]


  def encode(self, x):
    mean, logvar = self.encoder(x)
    return mean, logvar


  def decode(self, z):
    return self.decoder(z)


  def sample_from_latent_distribution(self, z_mean, z_logvar):
    """Samples from the Gaussian distribution defined by z_mean and z_logvar."""
    return tf.add(z_mean,
                  tf.exp(z_logvar / 2) * tf.random.normal(tf.shape(z_mean), 0, 1),
                  name="sampled_latent_variable")


  def _compute_losses(self, x, is_training=False):

    z_mean, z_logvar = self.encoder(x, training=is_training)
    z_sampled = self.sample_from_latent_distribution(z_mean, z_logvar)
    reconstructions = self.decoder(z_sampled, training=is_training)
    per_sample_loss = self.loss_fn(x, reconstructions)
    reconstruction_loss = tf.reduce_mean(per_sample_loss)
    kl_loss = compute_gaussian_kl(z_mean, z_logvar)
    regularizer = self.regularizer(kl_loss, z_mean, z_logvar, z_sampled)
    loss = tf.add(reconstruction_loss, regularizer, name="loss")
    elbo = tf.add(reconstruction_loss, kl_loss, name="elbo")

    return loss, reconstruction_loss, elbo


  def update_metrics(self, losses):
    for (loss_name, loss) in losses: self.metrics_dict[loss_name].update_state(loss)


  def train_step(self, data):
    """Executes one training step and returns the loss.
    This function computes the loss and gradients, and uses the latter to
    update the model's parameters.
    """
    x = data[0]
    with tf.GradientTape() as tape:
      loss, reconstruction_loss, elbo = self._compute_losses(x, is_training=True)

    gradients = tape.gradient(loss, self.trainable_variables)
    self.optimizer.apply_gradients(zip(gradients, self.trainable_variables))
    self.update_metrics([("loss", loss), ("reconstruction_loss", reconstruction_loss), ("elbo", elbo)])

    return {name : self.metrics_dict[name].result() for name in self.metric_names}


  def test_step(self, data):
    """Executes one test step and returns the loss.
    This function computes the loss, without updating the model parameters.
    """
    x = data[0]
    loss, reconstruction_loss, elbo = self.compute_losses(x, is_training=False)
    self.update_metrics([("loss", loss), ("reconstruction_loss", reconstruction_loss), ("elbo", elbo)])

    return {name : self.metrics_dict[name].result() for name in self.metric_names}


  def call(self, x, **kwargs):
    '''
    Here, we assume that calling the VAE model returns the encoder output, or the decoder output
    Default behaviour is to return the encoder output.
    To return the decoder output, pass the "decode" argument as True in the kwargs dict
    '''

    decode = kwargs.get("decode", False)
    z_mean, z_logvar = self.encoder(x, training=False)
    z_sampled = self.sample_from_latent_distribution(z_mean, z_logvar)

    if decode:
      reconstructions = self.decoder(z_sampled, training=False)
      return reconstructions
    else:
      return z_sampled


def compute_gaussian_kl(z_mean, z_logvar):
  """Compute KL divergence between input Gaussian and Standard Normal."""
  return tf.reduce_mean(
      0.5 * tf.reduce_sum(
          tf.square(z_mean) + tf.exp(z_logvar) - z_logvar - 1, [1]),
      name="kl_loss")

