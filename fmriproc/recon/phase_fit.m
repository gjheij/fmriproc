function [deltaB0map, Phi0map] = phase_fit(data, echotimes)
% PHASE_FIT  Estimate voxelwise B0 offset and phase intercept from multi-echo phase data
%
%   [deltaB0map, Phi0map] = phase_fit(data, echotimes)
%
%   Inputs:
%     data       [X×T×Ne] complex array of “jump-corrected” echoes
%     echotimes  [1×Ne] or [Ne×1] vector of echo times in seconds
%
%   Outputs:
%     deltaB0map [X×T]  estimated B0 offset (in Hz) per voxel
%     Phi0map    [X×T]  estimated phase at TE=0 (in radians) per voxel
%
%   Method:
%     1) Extract and unwrap phase along the echo dimension  
%        ph = unwrap(angle(data),[],3);
%     2) For each voxel/time, solve ph(TE) ≃ Phi0 + 2π·ΔB0·TE via least-squares  
%        [Phi0; 2π·ΔB0] = [1, TE]' \ ph  
%     3) Divide slope by 2π to get ΔB0 in Hz
%
%   (This matches Poser et al. 2006’s approach for multi-echo phase fitting.)

% dims
[X, T, Ne] = size(data);
TE = echotimes(:);             % [Ne×1]

% unwrap phase
ph = unwrap(angle(data), [], 3);  % still [X×T×Ne]

% reshape to [Ne × (X*T)]
PH = reshape(ph, X*T, Ne)';       % [Ne × (X*T)]

% design matrix: ph = [1, 2π·TE] · [Phi0; ΔB0]
A = [ones(Ne,1), 2*pi*TE];        % [Ne×2]

% LS fit for each voxel/time
B = A \ PH;                        % [2×(X*T)]

% unpack and reshape
Phi0  = B(1,:);                   % intercept in rad
dPhi  = B(2,:);                   % slope in rad/sec

Phi0map    = reshape(Phi0, X, T);      % [X×T]
deltaB0map = reshape(dPhi./(2*pi), X, T);  % convert rad/sec → Hz

end
