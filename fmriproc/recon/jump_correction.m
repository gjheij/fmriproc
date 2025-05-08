function data2 = jump_correction(data1, echo_dim)
  % Remove 2π jumps in the phase along the echo dimension
  ph = angle(data1);
  ph_unw = unwrap(ph,[],echo_dim);
  data2 = abs(data1) .* exp(1i*ph_unw);
end
