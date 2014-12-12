#!/usr/bin/env python

import os
import numpy as np
import scipy.stats as stats
import scipy.constants as const

# shorthands
pi,exp,sqrt = np.pi,np.exp,np.sqrt
c = const.c # m/s
c_kms = c/1e3
c_cms = c*1e2
sqrt_pi = sqrt(pi)
sigma_c = 6.33e-18 # cm^-2
fourpi = 4*pi

def _getlinelistdata():
	from astropy.io import fits
	# Line list obtained from Prochaska's XIDL code
	# https://svn.ucolick.org/xidl/trunk/Spec/Lines/all_lin.fits
	datadir = os.path.split(__file__)[0]+'/data/'
	linelist = fits.getdata(datadir+'all_lin.fits')
	Hlines = np.array([i for i in range(linelist.size) 
	                       if 'HI' in linelist.ION[i]])
	LySeries = {}
	for n in range(Hlines.size):
		LySeries[n+2] = Hlines[-1-n]
	return linelist,LySeries

linelist,LymanSeries = _getlinelistdata()

# default is to go up to 32->1
default_lymanseries_range = (2,33)

Fan99_model = {
  'forest':{'zrange':(0.0,6.0),
            'logNHrange':(13.0,17.3),
            'N0':50.3,
            'gamma':2.3,
            'beta':1.41,
            'b':30.0},
     'LLS':{'zrange':(0.0,6.0),
            'logNHrange':(17.3,20.5),
            'N0':0.27,
            'gamma':1.55,
            'beta':1.25,
            'b':70.0},
     'DLA':{'zrange':(0.0,6.0),
            'logNHrange':(20.5,22.0),
            'N0':0.04,
            'gamma':1.3,
            'beta':1.48,
            'b':70.0},
}

WP11_model = {
 'forest0':{'zrange':(0.0,1.5),
            'logNHrange':(12.0,19.0),
            'gamma':0.2,
            'beta':1.55,
            'B':0.0170,
            'N0':340.,
            'brange':(10.,100.),
            'bsig':24.0},
 'forest1':{'zrange':(1.5,4.6),
            'logNHrange':(12.0,14.5),
            'gamma':2.04,
            'beta':1.50,
            'B':0.0062,
            'N0':102.0,
            'brange':(10.,100.),
            'bsig':24.0},
 'forest2':{'zrange':(1.5,4.6),
            'logNHrange':(14.5,17.5),
            'gamma':2.04,
            'beta':1.80,
            'B':0.0062,
            'N0':4.05,
            'brange':(10.,100.),
            'bsig':24.0},
 'forest3':{'zrange':(1.5,4.6),
            'logNHrange':(17.5,19.0),
            'gamma':2.04,
            'beta':0.90,
            'B':0.0062,
            'N0':0.051,
            'brange':(10.,100.),
            'bsig':24.0},
    'SLLS':{'zrange':(0.0,4.6),
            'logNHrange':(19.0,20.3),
            'N0':0.0660,
            'gamma':1.70,
            'beta':1.40,
            'brange':(10.,100.),
            'bsig':24.0},
     'DLA':{'zrange':(0.0,4.6),
            'logNHrange':(20.3,22.0),
            'N0':0.0440,
            'gamma':1.27,
            'beta':2.00,
            'brange':(10.,100.),
            'bsig':24.0},
}

forestModels = {'Fan1999':Fan99_model,
                'Worseck&Prochaska2011':WP11_model}

def generate_los(model,zmin,zmax):
	'''Given a model for the distribution of absorption systems, generate
	   a random line-of-sight populated with absorbers.
	   returns (z,logNHI,b) for each absorption system.
	'''
	abs_dtype = [('z',np.float32),('logNHI',np.float32),('b',np.float32)]
	absorbers = []
	for component,p in model.items():
		if zmin > p['zrange'][1] or zmax < p['zrange'][0]:
			# outside the redshift range of this forest component
			continue
		# parameters for the forest component (LLS, etc.) absorber distribution
		NHImin,NHImax = p['logNHrange']
		NHImin,NHImax = 10**NHImin,10**NHImax
		z1 = max(zmin,p['zrange'][0])
		z2 = min(zmax,p['zrange'][1])
		beta = p['beta'] 
		mbeta1 = -beta+1
		gamma1 = p['gamma'] + 1
		# expectation for the number of absorbers at this redshift
		#  (inverting n(z) = N0*(1+z)^gamma)
		N = (p['N0']/gamma1) * ( (1+z2)**gamma1 - (1+z1)**gamma1 )
		# sample from a Poisson distribution for <N>
		n = stats.poisson.rvs(N,size=1)[0]
		# invert the dN/dz CDF to get the sample redshifts
		x = np.random.random_sample(n)
		z = (1+z1)*((((1+z2)/(1+z1))**gamma1 - 1)*x + 1)**(1/gamma1) - 1
		# invert the NHI CDF to get the sample column densities
		x = np.random.random_sample(n)
		NHI = NHImin*(1 + x*((NHImax/NHImin)**mbeta1 - 1))**(1/mbeta1)
		#
		try: 
			# fixed b
			b = np.array([p['b']]*n,dtype=np.float32)
		except KeyError:
			# dn/db ~ b^-5 exp(-(b/bsig)^-4) (Hui & Rutledge 1999)
			bsig = p['bsig']
			bmin,bmax = p['brange']
			bexp = lambda b: exp(-(b/bsig)**-4)
			x = np.random.random_sample(n)
			b = bsig*(-np.log((bexp(bmax)-bexp(bmin))*x + bexp(bmin)))**(-1./4)
		#
		absorber = np.empty(n,dtype=abs_dtype)
		absorber['z'] = z
		absorber['logNHI'] = np.log10(NHI)
		absorber['b'] = b
		absorbers.append(absorber)
	absorbers = np.concatenate(absorbers)
	# return sorted by redshift
	return absorbers[absorbers['z'].argsort()]

def voigt(a,x):
	'''Tepper-Garcia 2006, footnote 4 (see erratum)'''
	x2 = x**2
	Q = 1.5/x2
	H0 = exp(-x2)
	return H0 - (a/sqrt_pi)/x2 * (H0*H0*(4*x2*x2 + 7*x2 + 4 + Q) - Q - 1)

def sum_of_voigts(wave,tau_lam,c_voigt,a,lambda_z,b,tauMin,tauMax):
	umax = np.clip(np.sqrt(c_voigt * (a/sqrt_pi)/tauMin),5.0,np.inf)
	# ***assumes constant velocity bin spacings***
	dv = (wave[1]-wave[0])/(0.5*(wave[0]+wave[1])) * c_kms
	du = dv/b
	bnorm = b/c_kms
	npix = (umax/du).astype(np.int32)
	for i in range(len(a)):
		w0 = np.searchsorted(wave,lambda_z[i])
		i1 = max(0,w0-npix[i])
		i2 = min(len(wave),w0+npix[i])
		if np.all(tau_lam[i1:i2] > tauMax):
			continue
		# the clip is to prevent division by zero errors
		u = np.abs((wave[i1:i2]/lambda_z[i]-1)/bnorm[i]).clip(1e-5,np.inf)
		tau_lam[i1:i2] += c_voigt[i] * voigt(a[i],u)
	return tau_lam

# from http://stackoverflow.com/questions/42558/python-and-the-singleton-pattern
class Singleton:
	def __init__(self,decorated):
		self._decorated = decorated
	def Instance(self,*args,**kwargs):
		try:
			inst = self._instance
			#self._argcheck(*args)
		except AttributeError:
			self._instance = self._decorated(*args,**kwargs)
			inst = self._instance
		return inst
	def __call__(self):
		raise TypeError('Must be accessed through "Instance()".')
	def __instancecheck__(self,inst):
		return isinstance(inst,self._decorated)
	#def _argcheck(self,*args):
	#	raise NotImplementedError
@Singleton
class VoigtTable:
	def __init__(self,*args,**kwargs):
		self._init_table(*args,**kwargs)
	def _argcheck(self,*args):
		assert self.dv == args[0]
	def _init_table(self,*args,**kwargs):
		wave, = args
		# ***assumes constant velocity bin spacings***
		dv = (wave[1]-wave[0])/(0.5*(wave[0]+wave[1])) * c_kms
		self.wave0 = wave[0]
		self.npix = len(wave)
		self.dv = dv
		self.dv_c = dv/c_kms
		#
		na = kwargs.get('fastvoigt_na',20)
		loga_min = kwargs.get('fastvoigt_logamin',-8.5)
		loga_max = kwargs.get('fastvoigt_logamax',-3.0)
		gamma = kwargs.get('fastvoigt_gamma',1.5)
		nb = kwargs.get('fastvoigt_nb',20)
		u_range = kwargs.get('fastvoigt_urange',10)
		# define the bins in Voigt a parameter using exponential spacings
		alpha = (loga_max - loga_min) / na**gamma
		self.logabins = np.array([loga_max - alpha*n**gamma 
		                              for n in range(na)])
		# define the bins in b
		self.bbins = np.linspace(10.,100.,nb)
		# 
		self.xv = {}
		for j,b in enumerate(self.bbins):
			# offset slightly to avoid division by zero error
			self.xv[j] = np.arange(1e-5,u_range,dv/b)
		self.dx = np.array([len(self.xv[j])-1 for j in range(len(self.bbins))])
		self.voigt_tab = {}
		for i in range(na):
			self.voigt_tab[i] = {}
			for j in range(nb):
				vprof = voigt(10**self.logabins[i],self.xv[j])
				self.voigt_tab[i][j] = np.concatenate([vprof[::-1][1:],vprof])
	def sum_of_voigts(self,a,b,wave,c_voigt,tau_lam):
		ii = np.argmin(np.abs(np.log10(a)[:,np.newaxis] -
		               self.logabins[np.newaxis,:]),axis=1)
		jj = np.argmin(np.abs(b[:,np.newaxis]-self.bbins[np.newaxis,:]),axis=1)
		wc = np.round((np.log(wave) - np.log(self.wave0))/self.dv_c)
		wc = wc.astype(np.int32)
		dx = self.dx[jj]
		w1,w2 = wc-dx,wc+dx+1
		x1,x2 = np.zeros_like(dx),2*dx+1
		# off left edge of spectrum
		ll = np.where(w1<0)[0]
		x1[ll] = -w1[ll]
		w1[ll] = 0
		# off right edge of spectrum
		ll = np.where(w2>self.npix)[0]
		x2[ll] = self.npix - w1[ll]
		w2[ll] = self.npix
		# within the spectrum!
		ll = np.where(~((w2<0)|(w1>=self.npix)|(w2-w1<=0)))[0]
		# now loop over the absorbers and add the tabled voigt profiles
		for i,j,k in zip(ii[ll],jj[ll],ll):
			tau_lam[w1[k]:w2[k]] += \
			                  c_voigt[k] * self.voigt_tab[i][j][x1[k]:x2[k]]
		return tau_lam

def fast_sum_of_voigts(wave,tau_lam,c_voigt,a,lambda_z,b,
                       tauMin,tauMax,tauSplit):
	'''uses a  lookup table'''
	voigttab = VoigtTable.Instance(wave)
	# split out strong absorbers and do full calc
	ii = np.where(c_voigt >= tauSplit)[0]
	tau_lam = sum_of_voigts(wave,tau_lam,
	                        c_voigt[ii],a[ii],lambda_z[ii],b[ii],
	                        tauMin,tauMax)
	ii = np.where(c_voigt < tauSplit)[0]
	tau_lam = voigttab.sum_of_voigts(a[ii],b[ii],lambda_z[ii],
	                                 c_voigt[ii],tau_lam)
	return tau_lam

def sum_of_continuum_absorption(wave,tau_lam,NHI,z1,tauMin,tauMax):
	tau_c_lim = sigma_c*NHI
	lambda_z_c = 912.*z1
	ii = np.where((lambda_z_c > wave[0]) & (tau_c_lim > tauMin))[0]
	# sort by decreasing column density to start with highest tau systems
	ii = ii[NHI[ii].argsort()[::-1]]
	# ending pixel (wavelength at onset of continuum absorption)
	i_end = np.searchsorted(wave,lambda_z_c[ii],side='right')
	# starting pixel - wavelength where tau drops below tauMin
	wave_start = (tauMin/tau_c_lim[ii])**0.333 * wave[i_end]
	i_start = np.searchsorted(wave,wave_start)
	# now do the sum
	for i,i1,i2 in zip(ii,i_start,i_end):
		# ... only if pixels aren't already saturated
		if np.any(tau_lam[i1:i2] < tauMax):
			l1l0 = wave[i1:i2]/lambda_z_c[i]
			tau_lam[i1:i2] += tau_c_lim[i]*l1l0*l1l0*l1l0
	return tau_lam

def calc_tau_lambda(wave,los,**kwargs):
	lymanseries_range = kwargs.get('lymanseries_range',
	                               default_lymanseries_range)
	tauMax = kwargs.get('tauMax',15.0)
	tauMin = kwargs.get('tauMin',1e-5)
	tau_lam = kwargs.get('tauIn',np.zeros_like(wave))
	fast = kwargs.get('fast',True)
	tauSplit = kwargs.get('fast_tauSplit',1.0)
	# arrays of absorber properties
	NHI = 10**los['logNHI']
	z1 = 1 + los['z']
	b = los['b']
	# first apply continuum blanketing. the dense systems will saturate
	# a lot of the spectrum, obviating the need for calculations of
	# discrete transition profiles
	tau_lam = sum_of_continuum_absorption(wave,tau_lam,NHI,z1,tauMin,tauMax)
	# now loop over Lyman series transitions and add up Voigt profiles
	for transition in range(*lymanseries_range):
		# transition properties
		lambda0 = linelist.WREST[LymanSeries[transition]]
		F = linelist.F[LymanSeries[transition]]
		Gamma = linelist.GAMMA[LymanSeries[transition]]
		# Doppler width
		nu_D = b / (lambda0*1e-13)
		# Voigt a parameter
		a = Gamma / (fourpi*nu_D)
		# wavelength of transition at absorber redshift
		lambda_z = lambda0*z1
		# all the values used to calculate tau, now just needs line profile
		c_voigt = 0.014971475 * NHI * F / nu_D
		#
		#tau_lam[:] += continuum_absorption()
		if fast:
			tau_lam = fast_sum_of_voigts(wave,tau_lam,
			                             c_voigt,a,lambda_z,b,
			                             tauMin,tauMax,tauSplit)
		else:
			tau_lam = sum_of_voigts(wave,tau_lam,
			                        c_voigt,a,lambda_z,b,
			                        tauMin,tauMax)
	return tau_lam

def generate_spectra(wave,z_em,los,**kwargs):
	# default is 10 km/s
	forestRmin = kwargs.get('forestRmin',3e4)
	specR = (0.5*(wave[0]+wave[1]))/(wave[1]-wave[0])
	nrebin = np.int(np.ceil(forestRmin/specR))
	forestR = specR * nrebin
	# go a half pixel below the minimum wavelength
	wavemin = wave[0] - (wave[1]-wave[0])/2
	# go well beyond LyA to get maximum wavelength
	wavemax = min(wave[-1],1250*(1+z_em.max()))
	npix = np.searchsorted(wave,wavemax,side='right')
	fwave = np.exp(np.log(wavemin)+forestR**-1*np.arange(npix*nrebin))
	# only need absorbers up to the maximum redshift
	los = los[los['z']<z_em.max()]
	zi = np.concatenate([[0,],np.searchsorted(los['z'],z_em)])
	#
	tspec = np.ones(z_em.shape+wave.shape)
	#
	tau = np.zeros_like(fwave)
	for i in range(1,len(zi)):
		zi1,zi2 = zi[i-1],zi[i]
		tau = calc_tau_lambda(fwave,los[zi1:zi2],tauIn=tau,**kwargs)
		T = np.exp(-tau).reshape(-1,nrebin)
		tspec[i-1,:npix] = np.average(T,weights=fwave.reshape(-1,nrebin),
		                              axis=1)
	return tspec

def generate_N_spectra(wave,z_em,nlos,**kwargs):
	forestModel = kwargs.get('forestModel','Worseck&Prochaska2011')
	forestModel = forestModels[forestModel]
	zmin = kwargs.get('zmin',0.0)
	zmax = kwargs.get('zmax',z_em.max())
	specAll = np.zeros(z_em.shape+wave.shape)
	# map each emission redshift to a line-of-sight
	losMap = np.random.randint(0,nlos,z_em.shape[0])
	# generate spectra for each line-of-sight
	for losNum in range(nlos):
		ii = np.where(losMap == losNum)[0]
		zi = z_em[ii].argsort()
		los = generate_los(forestModel,zmin,zmax)
		spec = generate_spectra(wave,z_em[ii[zi]],los,**kwargs)
		specAll[ii,:] = spec[zi.argsort()]
	return specAll

