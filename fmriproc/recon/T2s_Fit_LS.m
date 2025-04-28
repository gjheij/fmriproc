function [T2s_fit, S0_fit] = T2s_Fit_LS(data, echotimes)
% T2s_Fit_LS  Fit mono-exponential decay S(TE)=S0·exp(-TE/T2*) by linear LS.
%
%   Inputs:
%     data        [X × Time × Ne] array of magnitudes (e.g. abs(data))
%     echotimes   [1 × Ne] or [Ne × 1] vector of echo times (same units)
%
%   Outputs:
%     T2s_fit     [X × Time] map of estimated T2* values
%     S0_fit      [X × Time] map of estimated S0 amplitudes

% get sizes
[ Nx, Nt, Ne ] = size(data);

% vector of TE
TE = echotimes(:);          % [Ne×1]

% build design matrix log S = log S0 - TE*(1/T2*)
A = [ ones(Ne,1),  -TE ];   % [Ne×2]

% reshape data to [Ne × (Nx*Nt)]
D = reshape(data, Nx*Nt, Ne)';   % now [Ne × (Nx*Nt)]

% avoid log(0)
D(D<=0) = eps;

% take logs
Y = log(D);                % [Ne × (Nx*Nt)]

% solve multi-response LS
B = A \ Y;                  % [2 × (Nx*Nt)]

% unpack
logS0 = B(1,:);             % [1 × (Nx*Nt)]
invT2 = B(2,:);             % [1 × (Nx*Nt)]

% reshape back to [Nx × Nt]
S0_fit  = reshape(exp(logS0), Nx, Nt);
T2s_fit = reshape(1./invT2, Nx, Nt);
end
