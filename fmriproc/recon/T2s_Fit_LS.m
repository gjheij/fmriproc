function [T2s_fit, S0_fit] = T2s_Fit_LS(data, echotimes)
    % T2s_Fit_LS - Fit mono-exponential decay model: S(TE) = S0 * exp(-TE/T2*)
    % via log-linear least squares.
    %
    % Inputs:
    %   data        [V × T × Ne] array of multi-echo magnitude data (e.g., abs(data))
    %   echotimes   [1 × Ne] or [Ne × 1] vector of echo times (same unit as desired T2*)
    %
    % Outputs:
    %   T2s_fit     [V × T] estimated T2* values (same units as echotimes)
    %   S0_fit      [V × T] estimated S0 amplitudes

    % Dimensions
    [V, T, Ne] = size(data);
    TE = echotimes(:);               % ensure [Ne × 1]

    % Build design matrix for log-linear fit
    A = [ones(Ne,1), -TE];           % [Ne × 2]

    % Reshape data for fitting: [Ne × (V*T)]
    D = reshape(data, V*T, Ne)';     % transpose to [Ne × (V*T)]
    D(D <= 0) = eps;                 % avoid log(0)

    % Log-transform
    Y = log(D);                      % [Ne × (V*T)]

    % Solve least squares: A * B = Y
    B = A \ Y;                       % [2 × (V*T)]

    % Extract parameters
    logS0 = B(1,:);                  % [1 × (V*T)]
    invT2 = B(2,:);                  % [1 × (V*T)]

    % Convert back
    S0_fit = reshape(exp(logS0), V, T);           % [V × T]
    T2s_fit = reshape(1 ./ invT2, V, T);          % [V × T]

    % Clean invalid fits
    T2s_fit(~isfinite(T2s_fit)) = 0;
    S0_fit(~isfinite(S0_fit)) = 0;

    end
